"""Tests for the Lab 04 simulator: unit conversions, parsing and the route.

Parsing tests build the same text files that ``wrdata`` writes, so they run
without ngspice. The integration class runs the real solver and is skipped
automatically when ngspice is not installed.
"""

import math
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import spice_engine
from app import app

FORM = dict(
    sp_vcc="12",
    sp_r1="100",
    sp_r2="22",
    sp_rc="2.2",
    sp_re="1",
    sp_rl="10",
    sp_cin="10",
    sp_cout="10",
    sp_amp="10",
    sp_freq="1000",
)


def si(**overrides):
    """Engine-side parameters (``vcc``, ``r1``...) with optional overrides."""
    values = {key[3:]: value for key, value in FORM.items()}
    values.update(overrides)
    return values


def has_engine():
    try:
        spice_engine.find_ngspice()
        return True
    except spice_engine.EngineMissing:
        return False


ENGINE_AVAILABLE = has_engine()


class TestParseParams(unittest.TestCase):
    def test_units_are_converted_to_si(self):
        params = spice_engine.parse_params(si())

        self.assertAlmostEqual(params.vcc, 12.0)
        self.assertAlmostEqual(params.r1, 100_000.0)
        self.assertAlmostEqual(params.re, 1_000.0)
        self.assertAlmostEqual(params.cin, 10e-6)
        self.assertAlmostEqual(params.amp, 10e-3)
        self.assertAlmostEqual(params.freq, 1_000.0)

    def test_zero_re_is_rejected_before_netlist(self):
        with self.assertRaises(ValueError) as ctx:
            spice_engine.parse_params(si(re="0"))

        self.assertIn("RE", str(ctx.exception))

    def test_non_numeric_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            spice_engine.parse_params(si(rc="abc"))

        self.assertIn("RC", str(ctx.exception))

    def test_out_of_range_frequency_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            spice_engine.parse_params(si(freq="999999999"))

        self.assertIn("Frequency", str(ctx.exception))


class TestNetlist(unittest.TestCase):
    def setUp(self):
        self.params = spice_engine.parse_params(si())

    def test_all_three_analyses_have_the_same_circuit(self):
        for analysis in ("dc", "ac", "tran"):
            netlist = spice_engine.build_netlist(self.params, analysis)
            for element in ("R1 vcc b", "R2 b 0", "RC vcc c", "RE e 0",
                            "Q1 c b e", "CIN src b", "COUT c out", "RL out 0"):
                self.assertIn(element, netlist)

    def test_analysis_directive_matches_request(self):
        self.assertIn("wrdata dc.dat", spice_engine.build_netlist(self.params, "dc"))
        self.assertIn("ac dec", spice_engine.build_netlist(self.params, "ac"))
        self.assertIn("wrdata tran.dat", spice_engine.build_netlist(self.params, "tran"))

    def test_unknown_analysis_is_rejected(self):
        with self.assertRaises(ValueError):
            spice_engine.build_netlist(self.params, "fft")


class TestParsersUseRealColumnLayout(unittest.TestCase):
    """Feed the exact column layout that ngspice ``wrdata`` produces."""

    def _artifacts(self, text, analysis):
        tmp = Path(tempfile.mkdtemp())
        data = tmp / f"{analysis}.dat"
        data.write_text(text, encoding="ascii")
        return spice_engine.RunArtifacts(
            analysis=analysis,
            directory=tmp,
            netlist=tmp / "circuit.cir",
            log=tmp / "run.log",
            data=data,
            engine="ngspice test",
            command=["ngspice"],
            elapsed_s=0.0,
        )

    def test_dc_parses_headers_and_derives_region(self):
        text = (
            " vcc  v(b)  v(e)  v(c)  @q1[ic]  @q1[ib]  @q1[ie]\n"
            " 1.2e+01 2.0e+00 1.3e+00 9.0e+00 1.4e-03 7.0e-06 1.4e-03\n"
        )
        data = spice_engine.parse_dc(self._artifacts(text, "dc"))

        self.assertAlmostEqual(data["vb"], 2.0)
        self.assertAlmostEqual(data["vce"], 7.7)
        self.assertAlmostEqual(data["ic"], 1.4e-3)
        self.assertEqual(data["region"], "active")

    def test_dc_flags_saturation_from_voltage(self):
        text = (
            " vcc  v(b)  v(e)  v(c)  @q1[ic]  @q1[ib]  @q1[ie]\n"
            " 1.2e+01 8.0e-01 7.0e-01 7.5e-01 5.0e-03 4.0e-05 5.0e-03\n"
        )
        data = spice_engine.parse_dc(self._artifacts(text, "dc"))

        self.assertAlmostEqual(data["vce"], 0.05)
        self.assertEqual(data["region"], "saturation")

    def test_ac_computes_gain_phase_and_corners(self):
        # Flat 10x gain between 100 Hz and 1 kHz; the outer points sit below
        # the -3 dB threshold, so both corners fall inside the sweep.
        text = (
            " frequency  v(out) v(out)  v(src) v(src)\n"
            " 1e+00 -1e+00 0e+00  1e+00 0e+00\n"
            " 1e+01 -2e+00 0e+00  1e+00 0e+00\n"
            " 1e+02 -1e+01 0e+00  1e+00 0e+00\n"
            " 1e+03 -1e+01 0e+00  1e+00 0e+00\n"
            " 1e+04 -2e+00 0e+00  1e+00 0e+00\n"
            " 1e+05 -1e+00 0e+00  1e+00 0e+00\n"
        )
        data = spice_engine.parse_ac(self._artifacts(text, "ac"))

        self.assertAlmostEqual(data["midband_gain"], 10.0)
        self.assertAlmostEqual(data["midband_gain_db"], 20.0)
        self.assertAlmostEqual(data["midband_phase"], 180.0)
        self.assertAlmostEqual(data["f_low"], 1e2)
        self.assertAlmostEqual(data["f_high"], 1e3)
        self.assertFalse(data["f_low_limited"])
        self.assertFalse(data["f_high_limited"])
        self.assertAlmostEqual(data["bandwidth"], 900.0)
        self.assertTrue(data["inverting"])

    def test_ac_reports_missing_corner_instead_of_inventing_one(self):
        text = (
            " frequency  v(out) v(out)  v(src) v(src)\n"
            " 1e+00 -1e+00 0e+00  1e+00 0e+00\n"
            " 1e+01 -1e+00 0e+00  1e+00 0e+00\n"
        )
        data = spice_engine.parse_ac(self._artifacts(text, "ac"))

        self.assertTrue(data["f_low_limited"] or data["f_high_limited"])

    def test_tran_measures_amplitude_and_inversion(self):
        rows = [" time  v(src)  v(out)"]
        for step in range(400):
            time_s = step * 1e-5
            vin = 0.01 * math.sin(2 * math.pi * 1000 * time_s)
            vout = -0.02 * math.sin(2 * math.pi * 1000 * time_s)
            rows.append(f" {time_s:.6e} {vin:.6e} {vout:.6e}")
        data = spice_engine.parse_tran(
            self._artifacts("\n".join(rows) + "\n", "tran")
        )

        self.assertAlmostEqual(data["gain"], 2.0, places=2)
        self.assertTrue(data["inverting"])
        self.assertAlmostEqual(data["vin_peak"], 0.01, places=3)


class FakeResult:
    """Build the dict shape that :func:`spice_engine.simulate` returns."""

    base = {
        "analysis": "dc",
        "analysis_label": "DC Operating Point",
        "command": ".op",
        "params": {"vcc": 12.0, "r1": 100_000.0, "r2": 22_000.0,
                   "rc": 2_200.0, "re": 1_000.0},
        "model": "Q2N2222",
        "model_source": "test card",
        "engine": "ngspice test · Q2N2222",
        "started_at": "2026-11-24T00:00:00+00:00",
        "elapsed_s": 0.12,
        "run_dir": "/tmp/run",
        "netlist": "* netlist",
        "log_tail": "No. of Data Rows : 1",
        "warnings": [],
        "data": {
            "vb": 2.0, "ve": 1.3, "vc": 9.0, "vce": 7.7,
            "ic": 1.3e-3, "ib": 7e-6, "ie": 1.3e-3, "region": "active",
        },
    }

    @classmethod
    def dc(cls):
        return dict(cls.base)

    @classmethod
    def ac(cls):
        result = dict(cls.base)
        result.update(analysis="ac", analysis_label="AC Frequency Response",
                      command=".ac dec")
        result["data"] = {
            "freq": [1.0, 10.0, 100.0],
            "gain": [1.0, 10.0, 1.0],
            "gain_db": [0.0, 20.0, 0.0],
            "phase": [180.0, 180.0, 180.0],
            "midband_gain": 10.0,
            "midband_gain_db": 20.0,
            "midband_phase": 180.0,
            "f_low": 1.0,
            "f_high": 100.0,
            "f_low_limited": False,
            "f_high_limited": False,
            "bandwidth": 99.0,
            "inverting": True,
        }
        return result

    @classmethod
    def tran(cls):
        result = dict(cls.base)
        result.update(analysis="tran", analysis_label="Transient Response",
                      command=".tran")
        result["data"] = {
            "time_s": [0.0, 0.001, 0.002],
            "vin": [0.0, 0.01, 0.0],
            "vout": [0.0, -0.02, 0.0],
            "vin_peak": 0.01,
            "vout_peak": 0.02,
            "vin_pp": 0.02,
            "vout_pp": 0.04,
            "gain": 2.0,
            "inverting": True,
            "tstop_ms": 2.0,
        }
        return result


class TestSimulatorRoute(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index_shows_simulator_form_and_three_analyses(self):
        body = self.client.get("/").get_data(as_text=True)

        for name in ("sp_vcc", "sp_r1", "sp_re", "sp_amp", "sp_freq"):
            self.assertIn(f'name="{name}"', body)
        for value in ("dc", "ac", "tran"):
            self.assertIn(f'value="{value}"', body)
        self.assertIn("ngspice", body)

    def test_invalid_re_shows_error_and_no_chart(self):
        res = self.client.post("/simulate", data=dict(FORM, sp_re="0", analysis="dc"))
        body = res.get_data(as_text=True)

        self.assertIn("Simulation Error", body)
        self.assertIn("RE", body)
        self.assertNotIn("<svg", body)

    def test_unknown_analysis_is_rejected(self):
        body = self.client.post(
            "/simulate", data=dict(FORM, analysis="fft")
        ).get_data(as_text=True)

        self.assertIn("Simulation Error", body)

    def test_dc_result_is_labelled_as_spice_and_shows_reference(self):
        with mock.patch.object(spice_engine, "simulate", return_value=FakeResult.dc()):
            body = self.client.post(
                "/simulate", data=dict(FORM, analysis="dc")
            ).get_data(as_text=True)

        self.assertIn("Success", body)
        self.assertIn("SPICE (ngspice)", body)
        self.assertIn("Analytical", body)
        self.assertIn("7.700 V", body)  # VCE from the (fake) run
        self.assertIn("ngspice", body)

    def test_ac_result_renders_chart_from_run_data(self):
        with mock.patch.object(spice_engine, "simulate", return_value=FakeResult.ac()):
            body = self.client.post(
                "/simulate", data=dict(FORM, analysis="ac")
            ).get_data(as_text=True)

        self.assertIn("<svg", body)
        self.assertIn("Bode", body)
        self.assertIn("10.000×", body)

    def test_tran_result_renders_waveform_chart(self):
        with mock.patch.object(spice_engine, "simulate", return_value=FakeResult.tran()):
            body = self.client.post(
                "/simulate", data=dict(FORM, analysis="tran")
            ).get_data(as_text=True)

        self.assertIn("<svg", body)
        self.assertIn("กลับเฟส", body)
        self.assertIn("20.00", body)  # Vout peak in mV

    def test_engine_failure_is_reported_without_stale_chart(self):
        error = spice_engine.EngineMissing("ไม่พบโปรแกรม ngspice")
        with mock.patch.object(spice_engine, "simulate", side_effect=error):
            body = self.client.post(
                "/simulate", data=dict(FORM, analysis="ac")
            ).get_data(as_text=True)

        self.assertIn("Simulation Error", body)
        self.assertIn("ไม่พบโปรแกรม ngspice", body)
        self.assertNotIn("<svg", body)


class TestRunLogClassification(unittest.TestCase):
    """Informational notes in a successful log must not fake a solver failure."""

    def setUp(self):
        self.params = spice_engine.parse_params(si())

    def _run_with_log(self, analysis: str, log_text: str):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        def fake_run(command, cwd, **kwargs):
            directory = Path(cwd)
            (directory / "run.log").write_text(log_text, encoding="utf-8")
            (directory / f"{analysis}.dat").write_text(
                "vcc v(b)\n12 1.9\n", encoding="utf-8"
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(
            spice_engine, "find_ngspice", return_value=Path("ngspice.exe")
        ), mock.patch("subprocess.run", side_effect=fake_run):
            return spice_engine.run(
                self.params, analysis, run_root=Path(tmp.name)
            )

    def test_spinit_note_is_not_a_failure(self):
        artifacts = self._run_with_log(
            "dc",
            "Note: can't find the initialization file spinit.\n"
            "\nNo. of Data Rows : 1\n",
        )
        self.assertTrue(artifacts.data.exists())

    def test_real_cant_find_error_is_still_reported(self):
        with self.assertRaises(spice_engine.SpiceRunFailed):
            self._run_with_log("dc", "Error: can't find model Q2N2222\n")


@unittest.skipUnless(ENGINE_AVAILABLE, "ngspice is not installed")
class TestRealNgspiceRuns(unittest.TestCase):
    """End-to-end checks against the real solver (slow but decisive)."""

    @classmethod
    def setUpClass(cls):
        cls.params = spice_engine.parse_params(si())

    def test_dc_run_matches_a_forward_active_operating_point(self):
        result = spice_engine.simulate(self.params, "dc")
        data = result["data"]

        self.assertGreater(data["ic"], 0.0)
        self.assertAlmostEqual(data["vce"], data["vc"] - data["ve"], places=6)
        self.assertEqual(data["region"], "active")
        self.assertIn("ngspice", result["engine"])

    def test_ac_run_reports_gain_and_corners_inside_sweep(self):
        data = spice_engine.simulate(self.params, "ac")["data"]

        self.assertTrue(0.5 < data["midband_gain"] < 50)
        self.assertLess(data["f_low"], data["f_high"])
        self.assertFalse(data["f_low_limited"])
        self.assertTrue(data["inverting"])

    def test_larger_re_lowers_collector_current(self):
        base = spice_engine.simulate(self.params, "dc")["data"]
        larger = spice_engine.simulate(
            spice_engine.parse_params(si(re="2")), "dc"
        )["data"]

        self.assertLess(larger["ic"], base["ic"])

    def test_transient_output_is_inverted_against_input(self):
        data = spice_engine.simulate(self.params, "tran")["data"]

        self.assertTrue(data["inverting"])
        self.assertAlmostEqual(data["vin_peak"], 0.01, places=4)

    def test_missing_engine_raises_instead_of_faking_success(self):
        with mock.patch.object(spice_engine, "find_ngspice",
                               side_effect=spice_engine.EngineMissing("ไม่มี engine")):
            with self.assertRaises(spice_engine.EngineMissing):
                spice_engine.simulate(self.params, "dc")


if __name__ == "__main__":
    unittest.main()
