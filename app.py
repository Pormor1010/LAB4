"""Flask front end for the BJT DC bias calculator and the Lab 04 simulator.

The HTTP layer only parses the form, converts kilo-ohms to ohms, picks the
function that matches the selected circuit and formats the numbers for
display. All engineering lives in :mod:`dc_bias` (analytical) and
:mod:`spice_engine` (real ngspice runs).
"""

from flask import Flask, render_template, request

import charts
import spice_engine
from dc_bias import BiasError, emitter_bias, fixed_bias, solve

app = Flask(__name__)

KILO = 1000.0  # kΩ -> Ω

DEFAULTS = {
    "vcc": "12",
    "r1": "100",
    "r2": "22",
    "rc": "2.2",
    "re": "1",
    "rb": "1000",
    "beta": "100",
    "vbe": "0.70",
}

# Field metadata: label, unit shown on the form and the Thai hint under it.
FIELDS = {
    "vcc": {"label": "VCC", "unit": "V", "hint": "แรงดันไฟเลี้ยง"},
    "rc": {"label": "RC", "unit": "kΩ", "hint": "ตัวต้านทานขา Collector"},
    "beta": {"label": "β (hFE)", "unit": "", "hint": "อัตราขยายกระแสตรง"},
    "vbe": {"label": "VBE", "unit": "V", "hint": "แรงดัน Base–Emitter"},
    "r1": {"label": "R1", "unit": "kΩ", "hint": "ตัวต้านทานขา Base ด้านบน"},
    "r2": {"label": "R2", "unit": "kΩ", "hint": "ตัวต้านทานขา Base ด้านล่าง"},
    "re": {"label": "RE", "unit": "kΩ", "hint": "ตัวต้านทานขา Emitter"},
    "rb": {"label": "RB", "unit": "kΩ", "hint": "ตัวต้านทานขา Base"},
}

COMMON_FIELDS = ("vcc", "rc", "beta", "vbe")

MODES = {
    "divider": {
        "label": "Voltage Divider Bias",
        "hint": "R1 จาก VCC ไป Base · R2 จาก Base ลงกราวด์ · "
        "RE จาก Emitter ลงกราวด์",
        "resistors": ("r1", "r2", "re"),
    },
    "fixed": {
        "label": "Fixed Bias",
        "hint": "RB จาก VCC ไป Base · Emitter ต่อลงกราวด์โดยตรง",
        "resistors": ("rb",),
    },
    "emitter": {
        "label": "Emitter Bias",
        "hint": "RB จาก VCC ไป Base · RE จาก Emitter ลงกราวด์",
        "resistors": ("rb", "re"),
    },
}


def _unknown_mode(mode):
    return (
        f"ข้อผิดพลาด: ไม่รู้จักโหมดวงจร “{mode}” — "
        "ต้องเป็น divider, fixed หรือ emitter"
    )


def _parse(form, mode):
    """Read only the fields the selected mode needs and return SI units."""

    def number(name):
        raw = (form.get(name) or "").strip()
        if not raw:
            raise ValueError(f"กรุณากรอกค่า {name.upper()}")
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"ค่า {name.upper()} ต้องเป็นตัวเลข") from None

    values = {
        "vcc": number("vcc"),
        "rc": number("rc") * KILO,
        "beta": number("beta"),
        "vbe": number("vbe"),
    }
    for name in MODES[mode]["resistors"]:
        values[name] = number(name) * KILO

    return values


def _solve(mode, values):
    """Pick the model that matches the selected circuit."""
    if mode == "divider":
        return solve(**values)
    if mode == "fixed":
        return fixed_bias(**values)
    if mode == "emitter":
        return emitter_bias(**values)
    raise BiasError(f"ไม่รู้จักโหมดวงจร {mode!r}")


def _display(result):
    """Format SI results for the page: volts, milliamps, microamps."""
    regions = {
        "active": "Active (ทำงานปกติ)",
        "saturation": "Saturation (อิ่มตัว)",
        "cutoff": "Cutoff (ตัดการนำ)",
    }
    return {
        "vb": f"{result['vb']:.3f}",
        "ve": f"{result['ve']:.3f}",
        "vc": f"{result['vc']:.3f}",
        "vce": f"{result['vce']:.3f}",
        "ic": f"{result['ic'] * 1000:.3f}",
        "ie": f"{result['ie'] * 1000:.3f}",
        "ib": f"{result['ib'] * 1e6:.3f}",
        "region": regions.get(result["region"], result["region"]),
    }


def _render(mode, form, result=None, error=None, warnings=None,
            sim=None, sim_error=None, sim_form=None, sim_analysis="dc"):
    ui_mode = mode if mode in MODES else "divider"
    return render_template(
        "index.html",
        mode=ui_mode,
        modes=MODES,
        fields=FIELDS,
        common_fields=COMMON_FIELDS,
        form=form,
        result=result,
        error=error,
        warnings=warnings or [],
        sim=sim,
        sim_error=sim_error,
        sim_form=sim_form or SIM_DEFAULTS,
        sim_analysis=sim_analysis,
        sim_fields=SIM_FIELDS,
        sim_groups=SIM_GROUPS,
        analyses=spice_engine.ANALYSES,
    )


# ---------------------------------------------------------------------------
# Lab 04 - CE voltage-divider simulator (real ngspice runs)
# ---------------------------------------------------------------------------

SIM_DEFAULTS = {
    "sp_vcc": "12",
    "sp_r1": "100",
    "sp_r2": "22",
    "sp_rc": "2.2",
    "sp_re": "1",
    "sp_rl": "10",
    "sp_cin": "10",
    "sp_cout": "10",
    "sp_amp": "10",
    "sp_freq": "1000",
}

SIM_FIELDS = {
    "vcc": {"label": "VCC", "unit": "V", "hint": "แรงดันไฟเลี้ยง"},
    "r1": {"label": "R1", "unit": "kΩ", "hint": "ตัวต้านทาน Base ด้านบน"},
    "r2": {"label": "R2", "unit": "kΩ", "hint": "ตัวต้านทาน Base ด้านล่าง"},
    "rc": {"label": "RC", "unit": "kΩ", "hint": "ตัวต้านทานขา Collector"},
    "re": {"label": "RE", "unit": "kΩ", "hint": "ตัวต้านทานขา Emitter (ไม่ bypass)"},
    "cin": {"label": "Cin", "unit": "µF", "hint": "คัปปลิงอินพุต"},
    "cout": {"label": "Cout", "unit": "µF", "hint": "คัปปลิงเอาต์พุต"},
    "rl": {"label": "RL", "unit": "kΩ", "hint": "โหลดฝั่งเอาต์พุต"},
    "amp": {"label": "Amplitude", "unit": "mV peak", "hint": "แอมปลิจูดแหล่งสัญญาณ"},
    "freq": {"label": "Frequency", "unit": "Hz", "hint": "ความถี่แหล่งสัญญาณ"},
}

SIM_GROUPS = (
    ("ไฟเลี้ยงและไบอัส", ("vcc", "r1", "r2", "rc", "re")),
    ("คัปปลิงและโหลด", ("cin", "cout", "rl")),
    ("แหล่งสัญญาณ (SIN)", ("amp", "freq")),
)

#: β/VBE used only to draw the Lab 3 analytical reference next to the SPICE
#: result. The BJT model card has its own BF, so the two are expected to
#: differ; the page labels both origins explicitly.
REFERENCE_BETA = 100.0
REFERENCE_VBE = 0.70


def _sim_values(form):
    """Collect the simulator inputs (``sp_*``) into engine field names."""
    return {name: form.get(f"sp_{name}") for name in SIM_FIELDS}


def _hz(value):
    """Format a frequency with an engineering prefix."""
    if value is None:
        return "ไม่พบในช่วง sweep"
    if value >= 1e6:
        return f"{value / 1e6:.3g} MHz"
    if value >= 1e3:
        return f"{value / 1e3:.3g} kHz"
    return f"{value:.3g} Hz"


def _present(result):
    """Turn an engine result into the values the template displays."""
    view = {
        "analysis": result["analysis"],
        "analysis_label": result["analysis_label"],
        "command": result["command"],
        "engine": result["engine"],
        "model": result["model"],
        "model_source": result["model_source"],
        "started_at": result["started_at"],
        "elapsed_s": f"{result['elapsed_s']:.2f}",
        "run_dir": result["run_dir"],
        "netlist": result["netlist"],
        "log_tail": result["log_tail"],
        "warnings": result["warnings"],
        "chart": None,
        "dc": None,
        "ac": None,
        "tran": None,
        "reference": None,
    }
    data = result["data"]

    if result["analysis"] == "dc":
        view["dc"] = _display(data)
        view["dc"]["vbe"] = f"{data['vb'] - data['ve']:.3f}"
        try:
            reference = solve(
                vcc=result["params"]["vcc"],
                r1=result["params"]["r1"],
                r2=result["params"]["r2"],
                rc=result["params"]["rc"],
                re=result["params"]["re"],
                beta=REFERENCE_BETA,
                vbe=REFERENCE_VBE,
            )
        except BiasError:
            reference = None
        if reference is not None:
            view["reference"] = _display(reference)
            view["reference"]["beta"] = f"{REFERENCE_BETA:g}"
            view["reference"]["vbe"] = f"{REFERENCE_VBE:.2f}"

    elif result["analysis"] == "ac":
        view["ac"] = {
            "midband_gain": f"{data['midband_gain']:.3f}",
            "midband_gain_db": f"{data['midband_gain_db']:.2f}",
            "midband_phase": f"{data['midband_phase']:.1f}",
            "f_low": _hz(data["f_low"]),
            "f_high": _hz(data["f_high"]),
            "bandwidth": (
                _hz(data["bandwidth"]) if data["bandwidth"] else "ไม่สามารถระบุได้"
            ),
            "inverting": data["inverting"],
            "points": f"{len(data['freq']):,}",
            "sweep": f"{_hz(data['freq'][0])} – {_hz(data['freq'][-1])}",
        }
        view["chart"] = charts.bode_svg(data)

    else:
        view["tran"] = {
            "vin_peak": f"{data['vin_peak'] * 1000:.2f}",
            "vout_peak": f"{data['vout_peak'] * 1000:.2f}",
            "gain": f"{data['gain']:.3f}",
            "inverting": data["inverting"],
            "tstop_ms": f"{data['tstop_ms']:.2f}",
            "points": f"{len(data['time_s']):,}",
        }
        view["chart"] = charts.waveform_svg(data)

    return view


@app.get("/")
def index():
    mode = request.args.get("mode", "divider")
    if mode not in MODES:
        return _render(mode, DEFAULTS, error=_unknown_mode(mode)), 400
    return _render(mode, DEFAULTS)


@app.post("/calculate")
def calculate():
    mode = (request.form.get("mode") or "").strip()
    if mode not in MODES:
        return _render(mode, request.form, error=_unknown_mode(mode)), 400

    try:
        params = _parse(request.form, mode)
        result = _solve(mode, params)
    except (TypeError, ValueError) as exc:
        return _render(mode, request.form, error=f"ข้อผิดพลาด: {exc}")

    return _render(
        mode,
        request.form,
        result=_display(result),
        warnings=result["warnings"],
    )


@app.post("/simulate")
def simulate():
    """Run one ngspice analysis for the reference CE circuit."""
    analysis = (request.form.get("analysis") or "dc").strip()
    values = _sim_values(request.form)
    mode = request.form.get("mode", "divider")
    ui_mode = mode if mode in MODES else "divider"
    # The simulator form carries hidden copies of the calculator inputs so the
    # unified results section can show the analytical result beside SPICE.
    # Missing values fall back to the documented defaults.
    dc_form = {
        key: request.form.get(key, DEFAULTS.get(key, ""))
        for key in (*COMMON_FIELDS, *MODES[ui_mode]["resistors"])
    }
    try:
        calc_result = _display(_solve(ui_mode, _parse(request.form, ui_mode)))
    except (TypeError, ValueError, BiasError):
        calc_result = None

    if analysis not in spice_engine.ANALYSES:
        return _render(
            mode,
            dc_form,
            result=calc_result,
            sim_form={f"sp_{key}": value for key, value in values.items()},
            sim_analysis="dc",
            sim_error=f"ไม่รู้จักโหมดวิเคราะห์ “{analysis}” — ต้องเป็น dc, ac หรือ tran",
        )

    sim_form = {f"sp_{key}": value for key, value in values.items()}
    try:
        params = spice_engine.parse_params(values)
        result = spice_engine.simulate(params, analysis)
    except (TypeError, ValueError) as exc:
        return _render(
            mode,
            dc_form,
            result=calc_result,
            sim_form=sim_form,
            sim_analysis=analysis,
            sim_error=f"ข้อมูลไม่ถูกต้อง: {exc}",
        )
    except spice_engine.SpiceError as exc:
        return _render(
            mode,
            dc_form,
            result=calc_result,
            sim_form=sim_form,
            sim_analysis=analysis,
            sim_error=str(exc),
        )
    except OSError as exc:
        return _render(
            mode,
            dc_form,
            result=calc_result,
            sim_form=sim_form,
            sim_analysis=analysis,
            sim_error=f"เรียก ngspice ไม่สำเร็จ: {exc}",
        )

    return _render(
        mode,
        dc_form,
        result=calc_result,
        sim_form=sim_form,
        sim_analysis=analysis,
        sim=_present(result),
    )

