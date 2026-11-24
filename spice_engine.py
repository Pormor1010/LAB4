"""ngspice adapter for the Lab 04 Common-Emitter voltage-divider reference.

This module owns everything that talks to the SPICE solver: parameter
validation, netlist generation, launching the external ``ngspice`` process
and parsing the numbers it writes back. It knows nothing about Flask, HTTP
or HTML; :mod:`app` converts form strings to SI units and renders the result.

Engineering reference (one fixed circuit, no free-form editor):

    VCC --+-- R1 --+-- RC --+---- Cout ----+---- RL ----+
          |        |        |              |            |
          |        b        c              out          |
          |        |        |              |            |
         R2        Q1       |              |            |
          |        |        |              |            |
         GND       e        |              |            |
                   |        |              |            |
                  RE        |              |            |
                   |        |              |            |
                  GND       |              |            |
                            |              |            |
    VS ~ -- Cin -- b        +--------------+            |
                                                        |
                                                       GND

Measurement convention used by every analysis:

* ``vin``  is the source node ``src`` (before ``Cin``), not the base node.
* ``vout`` is the load node ``out`` (after ``Cout``, across ``RL``).
* Gain is therefore ``|V(out) / V(src)|`` and phase is
  ``arg(V(out)) - arg(V(src))``.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Circuit / model constants (documented in README + docs/validation.md)
# --------------------------------------------------------------------------

#: NPN model used for every SPICE run. The Lab 04 starter kit was not
#: supplied for this project, so a public, widely published 2N2222 model
#: (Philips datasheet parameters as shipped with ngspice examples) is used.
#: It is written into every netlist so a run is reproducible from the file.
MODEL_NAME = "Q2N2222"
MODEL_CARD = (
    ".model Q2N2222 NPN(IS=1E-14 VAF=100 BF=200 IKF=0.3 XTB=1.5 BR=3 "
    "CJC=8E-12 CJE=25E-12 TR=100E-9 TF=400E-12 ITF=1 VTF=2 XTF=3 RB=10 "
    "RC=.3 RE=.2)"
)
MODEL_SOURCE = "2N2222 NPN (Philips parameters, standard ngspice example card)"

ANALYSES = {
    "dc": {
        "command": ".op",
        "title": "DC Operating Point",
        "notation": ".op",
    },
    "ac": {
        "command": ".ac dec",
        "title": "AC Frequency Response",
        "notation": ".ac",
    },
    "tran": {
        "command": ".tran",
        "title": "Transient Response",
        "notation": ".tran",
    },
}

SWEEP_START_HZ = 0.1
SWEEP_STOP_HZ = 100e6
SWEEP_POINTS_PER_DECADE = 20

TRAN_PERIODS = 5          # how many input cycles to simulate
TRAN_STEPS_PER_PERIOD = 200

DEFAULT_TIMEOUT = 60.0    # seconds per ngspice run

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class SpiceError(RuntimeError):
    """Base class for every solver-side failure shown to the user."""


class EngineMissing(SpiceError):
    """ngspice executable was not found on this machine."""


class SpiceTimeout(SpiceError):
    """A run exceeded :data:`DEFAULT_TIMEOUT`."""


class SpiceRunFailed(SpiceError):
    """ngspice exited with an error or produced no usable output."""


class SpiceParseError(SpiceError):
    """ngspice output existed but could not be read as numbers."""


# --------------------------------------------------------------------------
# Locating the solver
# --------------------------------------------------------------------------


def find_ngspice() -> Path:
    """Return the path of the ngspice executable.

    Search order: ``NGSPICE_BIN`` environment variable, the bundled copy in
    ``tools/ngspice/Spice64/bin``, then ``PATH``. Raises
    :class:`EngineMissing` when nothing is found so the caller can render a
    real error instead of pretending a run happened.
    """
    override = os.environ.get("NGSPICE_BIN")
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate
        raise EngineMissing(
            "Environment variable NGSPICE_BIN ชี้ไปที่ไฟล์ที่ไม่มีอยู่: "
            f"{candidate}"
        )

    bundled = (
        Path(__file__).resolve().parent
        / "tools"
        / "ngspice"
        / "Spice64"
        / "bin"
        / "ngspice.exe"
    )
    if bundled.is_file():
        return bundled

    on_path = shutil.which("ngspice")
    if on_path:
        return Path(on_path)

    raise EngineMissing(
        "ไม่พบโปรแกรม ngspice — ติดตั้ง ngspice แล้วเพิ่มลง PATH "
        "หรือตั้งค่า Environment variable NGSPICE_BIN ให้ชี้ไปที่ ngspice.exe"
    )


def engine_version() -> str:
    """Return the version banner of the detected engine.

    ``ngspice -v`` on the Windows console build waits for interactive input,
    so the probe runs a tiny netlist with the ngspice ``version`` command
    instead and reads the banner it writes to the log.
    """
    exe = find_ngspice()
    probe = (
        "* version probe\n"
        "V1 1 0 1\n"
        "R1 1 0 1k\n"
        ".control\n"
        "version\n"
        ".endc\n"
        ".end\n"
    )
    try:
        with tempfile.TemporaryDirectory(prefix="ngspice_probe_") as tmp:
            directory = Path(tmp)
            (directory / "v.cir").write_text(probe, encoding="ascii")
            subprocess.run(
                [str(exe), "-b", "-o", "v.log", "v.cir"],
                cwd=str(directory),
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                errors="replace",
                stdin=subprocess.DEVNULL,
            )
            log_file = directory / "v.log"
            text = (
                log_file.read_text(encoding="utf-8", errors="replace")
                if log_file.exists()
                else ""
            )
    except (OSError, subprocess.SubprocessError):
        return "ngspice (อ่านรุ่นไม่ได้)"

    match = re.search(r"ngspice-([0-9]+(?:\.[0-9]+)*)", text)
    if match:
        return f"ngspice {match.group(1)}"
    return "ngspice (อ่านรุ่นไม่ได้)"


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CeParams:
    """Validated SI parameters of the reference CE amplifier."""

    vcc: float          # V
    r1: float           # ohm
    r2: float           # ohm
    rc: float           # ohm
    re: float           # ohm
    rl: float           # ohm
    cin: float          # F
    cout: float         # F
    amp: float          # V peak of the signal source
    freq: float         # Hz

    def as_dict(self) -> dict[str, float]:
        return {
            "vcc": self.vcc,
            "r1": self.r1,
            "r2": self.r2,
            "rc": self.rc,
            "re": self.re,
            "rl": self.rl,
            "cin": self.cin,
            "cout": self.cout,
            "amp": self.amp,
            "freq": self.freq,
        }


#: name -> (label, unit, min, max) for SPICE-only inputs. Bounds keep the
#: solver inside a sane region; they are checked before a netlist is written.
LIMITS = {
    "vcc": ("VCC", "V", 0.5, 60.0),
    "r1": ("R1", "kΩ", 0.1, 10_000.0),
    "r2": ("R2", "kΩ", 0.1, 10_000.0),
    "rc": ("RC", "kΩ", 0.01, 100.0),
    "re": ("RE", "kΩ", 0.01, 100.0),
    "rl": ("RL", "kΩ", 0.01, 1_000.0),
    "cin": ("Cin", "µF", 0.001, 10_000.0),
    "cout": ("Cout", "µF", 0.001, 10_000.0),
    "amp": ("Amplitude", "mV peak", 0.1, 5_000.0),
    "freq": ("Frequency", "Hz", 1.0, 5e6),
}


def _number(name: str, raw) -> float:
    label = LIMITS[name][0]
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise ValueError(f"กรุณากรอกค่า {label}")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"ค่า {label} ต้องเป็นตัวเลข") from None
    if not math.isfinite(value):
        raise ValueError(f"ค่า {label} ต้องเป็นจำนวนจริงที่จำกัด")
    return value


def parse_params(form) -> CeParams:
    """Read the simulator form and return SI-valued parameters.

    Resistors/capacitors arrive in kΩ and µF, the source amplitude in mV
    peak. Everything is converted here so the netlist is written in SI.
    """
    raw = {name: _number(name, form.get(name)) for name in LIMITS}
    for name, (label, unit, low, high) in LIMITS.items():
        if not low <= raw[name] <= high:
            raise ValueError(
                f"ค่า {label} ต้องอยู่ระหว่าง {low:g}–{high:g} {unit}"
            )

    re_ohm = raw["re"] * 1000.0
    if re_ohm < 1.0:
        raise ValueError("ค่า RE ต้องไม่น้อยกว่า 1 Ω (ห้ามเป็น 0)")

    return CeParams(
        vcc=raw["vcc"],
        r1=raw["r1"] * 1000.0,
        r2=raw["r2"] * 1000.0,
        rc=raw["rc"] * 1000.0,
        re=re_ohm,
        rl=raw["rl"] * 1000.0,
        cin=raw["cin"] * 1e-6,
        cout=raw["cout"] * 1e-6,
        amp=raw["amp"] * 1e-3,
        freq=raw["freq"],
    )


# --------------------------------------------------------------------------
# Netlist
# --------------------------------------------------------------------------


def build_netlist(params: CeParams, analysis: str) -> str:
    """Return a complete ngspice netlist for one analysis.

    The circuit is identical for all three analyses; only the control block
    changes. ``.control`` + ``wrdata`` is used (instead of binary raw files)
    because the generated text files are deterministic, easy to audit and
    contain column names.
    """
    if analysis not in ANALYSES:
        raise ValueError(f"ไม่รู้จักโหมดวิเคราะห์ {analysis!r}")

    period = 1.0 / params.freq
    tstop = TRAN_PERIODS * period
    tstep = period / TRAN_STEPS_PER_PERIOD

    if analysis == "dc":
        body = """
.control
set wr_vecnames
set wr_singlescale
op
wrdata dc.dat vcc v(b) v(e) v(c) @q1[ic] @q1[ib] @q1[ie]
.endc
"""
    elif analysis == "ac":
        body = f"""
.control
set wr_vecnames
set wr_singlescale
ac dec {SWEEP_POINTS_PER_DECADE} {SWEEP_START_HZ:g} {SWEEP_STOP_HZ:g}
wrdata ac.dat v(out) v(src)
.endc
"""
    else:
        body = f"""
.control
set wr_vecnames
set wr_singlescale
tran {tstep:.10g} {tstop:.10g}
wrdata tran.dat v(src) v(out)
.endc
"""

    return f"""* Lab 04 CE voltage-divider amplifier - {analyses_label(analysis)}
* Single reference circuit; generated by spice_engine.py - do not edit by hand
* Model: {MODEL_NAME} ({MODEL_SOURCE})
VCC vcc 0 {params.vcc:.10g}
R1 vcc b {params.r1:.10g}
R2 b 0 {params.r2:.10g}
RC vcc c {params.rc:.10g}
RE e 0 {params.re:.10g}
Q1 c b e {MODEL_NAME}
VS src 0 DC 0 AC 1 SIN(0 {params.amp:.10g} {params.freq:.10g})
CIN src b {params.cin:.10g}
COUT c out {params.cout:.10g}
RL out 0 {params.rl:.10g}
{MODEL_CARD}
{body}.end
"""


def analyses_label(analysis: str) -> str:
    """Human label of an analysis code (``dc`` -> ``DC Operating Point``)."""
    try:
        return ANALYSES[analysis]["title"]
    except KeyError:
        return analysis


# --------------------------------------------------------------------------
# Running the solver
# --------------------------------------------------------------------------


@dataclass
class RunArtifacts:
    """Files and metadata produced by one ngspice invocation."""

    analysis: str
    directory: Path
    netlist: Path
    log: Path
    data: Path
    engine: str
    command: list[str]
    elapsed_s: float
    stdout: str = ""
    stderr: str = ""
    started_at: str = ""


def _default_run_root() -> Path:
    root = Path(__file__).resolve().parent / "instance" / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _prune_runs(root: Path, keep: int = 30) -> None:
    """Keep only the newest ``keep`` run directories so the tree stays small."""
    try:
        dirs = sorted(
            (p for p in root.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for old in dirs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def run(params: CeParams, analysis: str, run_root: Path | None = None,
        timeout: float = DEFAULT_TIMEOUT) -> RunArtifacts:
    """Run one analysis with ngspice and return where its output landed.

    * arguments are passed as a list (no ``shell=True``),
    * each run gets its own working directory, because ``wrdata`` writes
      relative to the process working directory,
    * ``timeout`` is enforced and reported as :class:`SpiceTimeout`.
    """
    if analysis not in ANALYSES:
        raise ValueError(f"ไม่รู้จักโหมดวิเคราะห์ {analysis!r}")

    exe = find_ngspice()
    root = Path(run_root) if run_root else _default_run_root()
    root.mkdir(parents=True, exist_ok=True)
    _prune_runs(root)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    directory = Path(tempfile.mkdtemp(prefix=f"{stamp}_{analysis}_", dir=root))

    netlist = directory / "circuit.cir"
    log = directory / "run.log"
    data = directory / f"{analysis}.dat"
    netlist.write_text(build_netlist(params, analysis), encoding="ascii")

    command = [
        str(exe),
        "-b",
        "-o",
        log.name,
        "-r",
        f"{analysis}.raw",
        netlist.name,
    ]
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    began = datetime.now()

    try:
        proc = subprocess.run(
            command,
            cwd=str(directory),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise SpiceTimeout(
            f"ngspice ใช้เวลาเกิน {timeout:g} วินาที จึงหยุดการทำงาน "
            f"(โฟลเดอร์รัน: {directory})"
        ) from None
    except OSError as exc:
        raise EngineMissing(f"เรียก ngspice ไม่สำเร็จ: {exc}") from None

    elapsed = (datetime.now() - began).total_seconds()
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""

    if proc.returncode != 0:
        raise SpiceRunFailed(
            f"ngspice จบด้วย exit code {proc.returncode}\n"
            f"{_log_tail(log_text)}"
        )
    # ngspice writes harmless diagnostics as "Note: ..." lines, e.g. a missing
    # optional spinit file. Only scan real report lines so those notes cannot
    # be mistaken for a failed run while genuine solver errors still surface.
    report_lines = [
        line for line in log_text.splitlines()
        if not line.lstrip().startswith("Note:")
    ]
    report_text = "\n".join(report_lines)
    for pattern in ("Error:", "fatal error", "no such vector", "can't find"):
        if pattern.lower() in report_text.lower():
            raise SpiceRunFailed(
                f"ngspice รายงานข้อผิดพลาด: {pattern}\n{_log_tail(log_text)}"
            )

    if not data.exists() or data.stat().st_size == 0:
        raise SpiceRunFailed(
            "ngspice ไม่ได้สร้างไฟล์ผลลัพธ์ (ข้อมูลว่าง)\n" + _log_tail(log_text)
        )

    return RunArtifacts(
        analysis=analysis,
        directory=directory,
        netlist=netlist,
        log=log,
        data=data,
        engine=f"{engine_version()} · {MODEL_NAME}",
        command=command,
        elapsed_s=elapsed,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        started_at=started,
    )


def _log_tail(text: str, lines: int = 6) -> str:
    kept = [ln for ln in text.strip().splitlines() if ln.strip()][-lines:]
    return "\n".join(kept) if kept else "(ไม่มีข้อความจาก ngspice)"


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _read_columns(path: Path) -> tuple[list[str], list[list[float]]]:
    """Read a ``wrdata`` text file into a header list and numeric columns."""
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise SpiceParseError(f"อ่านไฟล์ผลลัพธ์ไม่ได้: {exc}") from None

    rows = [ln for ln in raw_lines if ln.strip()]
    if len(rows) < 2:
        raise SpiceParseError("ไฟล์ผลลัพธ์มีข้อมูลไม่พอสำหรับการอ่านค่า")

    header = rows[0].split()
    columns: list[list[float]] = []
    for line in rows[1:]:
        cells = line.split()
        try:
            values = [float(cell) for cell in cells]
        except ValueError:
            raise SpiceParseError(
                f"พบข้อมูลที่ไม่ใช่ตัวเลขในไฟล์ผลลัพธ์: {line[:60]}"
            ) from None
        if not columns:
            columns = [[] for _ in values]
        if len(values) != len(columns):
            raise SpiceParseError("จำนวนคอลัมน์ในไฟล์ผลลัพธ์ไม่สม่ำเสมอ")
        for index, value in enumerate(values):
            columns[index].append(value)
    return header, columns


def _midband_phase(phase: list[float], gain: list[float]) -> float:
    """Phase at the frequency where the gain is highest (midband)."""
    if not gain:
        return 0.0
    return phase[gain.index(max(gain))]


def _frequencies(path: Path) -> list[float]:
    _, columns = _read_columns(path)
    return columns[0]


def parse_dc(artifacts: RunArtifacts) -> dict:
    """Turn the ``.op`` text file into the operating point shown on the page."""
    header, columns = _read_columns(artifacts.data)
    if not header or not columns:
        raise SpiceParseError("ไม่พบข้อมูล Operating Point")

    first = {name: columns[index][0] for index, name in enumerate(header) if index < len(columns)}
    required = ("v(b)", "v(e)", "v(c)", "@q1[ic]", "@q1[ib]", "@q1[ie]")
    missing = [key for key in required if key not in first]
    if missing:
        raise SpiceParseError(
            "ผล .op ไม่มีค่าที่ต้องใช้: " + ", ".join(missing)
        )

    vb = first["v(b)"]
    ve = first["v(e)"]
    vc = first["v(c)"]
    ic = abs(first["@q1[ic]"])
    ib = abs(first["@q1[ib]"])
    ie = abs(first["@q1[ie]"])
    vce = vc - ve

    if ic < 1e-9:
        region = "cutoff"
    elif vce < 0.2:
        region = "saturation"
    else:
        region = "active"

    return {
        "vb": vb,
        "ve": ve,
        "vc": vc,
        "vce": vce,
        "ic": ic,
        "ib": ib,
        "ie": ie,
        "region": region,
    }


def parse_ac(artifacts: RunArtifacts) -> dict:
    """Return Bode data plus the -3 dB corners found inside the sweep.

    Column layout is written by :func:`build_netlist`::

        frequency  v(out)_re v(out)_im  v(src)_re v(src)_im
    """
    header, columns = _read_columns(artifacts.data)
    if len(columns) < 5:
        raise SpiceParseError(
            "ผล .ac ต้องมี 5 คอลัมน์ (frequency, v(out), v(src))"
        )

    freq = columns[0]
    out_re, out_im = columns[1], columns[2]
    src_re, src_im = columns[3], columns[4]

    gain: list[float] = []
    phase: list[float] = []
    for index in range(len(freq)):
        out_mag = math.hypot(out_re[index], out_im[index])
        src_mag = math.hypot(src_re[index], src_im[index])
        gain.append(out_mag / src_mag if src_mag else 0.0)
        phase.append(
            math.degrees(
                math.atan2(out_im[index], out_re[index])
                - math.atan2(src_im[index], src_re[index])
            )
        )

    # Unwrap phase so the plotted curve is continuous.
    for index in range(1, len(phase)):
        while phase[index] - phase[index - 1] > 180:
            phase[index] -= 360
        while phase[index] - phase[index - 1] < -180:
            phase[index] += 360

    gain_db = [20 * math.log10(value) if value > 0 else -300.0 for value in gain]

    peak = max(gain) if gain else 0.0
    threshold = peak / math.sqrt(2)
    f_low = None
    for index, value in enumerate(gain):
        if value >= threshold:
            f_low = freq[index]
            break
    f_high = None
    for index in range(len(gain) - 1, -1, -1):
        if gain[index] >= threshold:
            f_high = freq[index]
            break

    low_limited = f_low is not None and f_low <= freq[0]
    high_limited = f_high is not None and f_high >= freq[-1]

    return {
        "freq": freq,
        "gain": gain,
        "gain_db": gain_db,
        "phase": phase,
        "midband_gain": peak,
        "midband_gain_db": 20 * math.log10(peak) if peak > 0 else float("-inf"),
        "midband_phase": _midband_phase(phase, gain),
        "f_low": f_low,
        "f_high": f_high,
        "f_low_limited": low_limited,
        "f_high_limited": high_limited,
        "bandwidth": (f_high - f_low) if f_low is not None and f_high is not None else None,
        "inverting": abs(_midband_phase(phase, gain)) > 90,
    }


def parse_tran(artifacts: RunArtifacts) -> dict:
    """Return time-domain input/output traces and their measured amplitudes.

    Column layout: ``time  v(src)  v(out)`` (seconds, volts).
    """
    header, columns = _read_columns(artifacts.data)
    if len(columns) < 3:
        raise SpiceParseError("ผล .tran ต้องมี 3 คอลัมน์ (time, v(src), v(out))")

    time_s = columns[0]
    vin = columns[1]
    vout = columns[2]
    if len(time_s) < 10:
        raise SpiceParseError("ผล .tran มีจุดข้อมูลน้อยเกินไป")

    # Use the second half of the window so the coupling capacitors have
    # settled; the numbers on the page are steady-state, not start-up.
    start = len(time_s) // 2
    vin_win = vin[start:]
    vout_win = vout[start:]

    vin_pp = max(vin_win) - min(vin_win)
    vout_pp = max(vout_win) - min(vout_win)
    vin_peak = vin_pp / 2
    vout_peak = vout_pp / 2
    gain = (vout_peak / vin_peak) if vin_peak > 1e-12 else 0.0

    mean_in = sum(vin_win) / len(vin_win)
    mean_out = sum(vout_win) / len(vout_win)
    covariance = sum(
        (a - mean_in) * (b - mean_out) for a, b in zip(vin_win, vout_win)
    )
    inverting = covariance < 0

    return {
        "time_s": time_s,
        "vin": vin,
        "vout": vout,
        "vin_peak": vin_peak,
        "vout_peak": vout_peak,
        "vin_pp": vin_pp,
        "vout_pp": vout_pp,
        "gain": gain,
        "inverting": inverting,
        "tstop_ms": time_s[-1] * 1000.0,
    }


PARSERS = {"dc": parse_dc, "ac": parse_ac, "tran": parse_tran}


def simulate(params: CeParams, analysis: str, run_root: Path | None = None,
             timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Run one analysis and return a JSON-friendly result dictionary."""
    artifacts = run(params, analysis, run_root=run_root, timeout=timeout)
    parsed = PARSERS[analysis](artifacts)
    return {
        "analysis": analysis,
        "analysis_label": analyses_label(analysis),
        "command": ANALYSES[analysis]["command"],
        "params": params.as_dict(),
        "model": MODEL_NAME,
        "model_source": MODEL_SOURCE,
        "engine": artifacts.engine,
        "started_at": artifacts.started_at,
        "elapsed_s": round(artifacts.elapsed_s, 3),
        "run_dir": str(artifacts.directory),
        "netlist": artifacts.netlist.read_text(encoding="ascii", errors="replace"),
        "log_tail": _log_tail(
            artifacts.log.read_text(encoding="utf-8", errors="replace")
        ),
        "data": parsed,
        "warnings": spice_warnings(analysis, parsed),
    }


def spice_warnings(analysis: str, data: dict) -> list[str]:
    """Engineering warnings derived from a completed run (never invented)."""
    messages: list[str] = []
    if analysis == "dc":
        if data["region"] == "saturation":
            messages.append(
                "VCE ต่ำกว่า 0.2 V — ngspice วางวงจรไว้ใน Saturation "
                "ค่าขยายจาก .ac ในสภาวะนี้ไม่ใช่ Small-Signal ปกติ"
            )
        elif data["region"] == "cutoff":
            messages.append(
                "IC ใกล้ศูนย์ — ngspice วางวงจรไว้ใน Cutoff "
                "ไม่มีการขยายสัญญาณในสภาวะนี้"
            )
    elif analysis == "ac":
        if data["f_low_limited"]:
            messages.append(
                f"จุดตัด -3 dB ด้านต่ำอยู่นอกช่วง sweep "
                f"(≤ {SWEEP_START_HZ:g} Hz) — ต้องกวาดความถี่ต่ำกว่านี้"
            )
        if data["f_high_limited"]:
            messages.append(
                f"จุดตัด -3 dB ด้านสูงอยู่นอกช่วง sweep "
                f"(≥ {SWEEP_STOP_HZ:g} Hz) — ต้องกวาดความถี่สูงกว่านี้"
            )
        if data["midband_gain"] < 1:
            messages.append(
                "อัตราขยายย่านกลางน้อยกว่า 1 (0 dB) — วงจรนี้ลดสัญญาณ "
                "ให้ตรวจค่า RC/RE/RL อีกครั้ง"
            )
    elif analysis == "tran":
        if data["gain"] < 1:
            messages.append(
                "แอมปลิจูดฝั่งออกเล็กกว่าฝั่งเข้า — ตรวจค่าไบอัสและโหลด"
            )
    return messages
