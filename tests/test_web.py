"""HTTP-level tests for the Flask routes."""

import unittest
from unittest import mock

from app import app


class TestIndex(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_get_index_shows_form(self):
        res = self.client.get("/")

        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        for field in ("vcc", "r1", "r2", "rc", "re", "beta", "vbe"):
            self.assertIn(f'name="{field}"', body)


class TestCalculate(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.valid = dict(
            mode="divider",
            vcc="12",
            r1="100",
            r2="22",
            rc="2.2",
            re="1",
            beta="100",
            vbe="0.70",
        )

    def test_post_returns_computed_values(self):
        res = self.client.post("/calculate", data=self.valid)

        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("8.052", body)  # VCE
        self.assertIn("1.230", body)  # IC in mA
        self.assertIn("1.942", body)  # VB


class TestUnifiedResults(unittest.TestCase):
    """The analytical and SPICE results must render in one results section."""

    def setUp(self):
        self.client = app.test_client()
        self.dc = dict(
            mode="divider", vcc="12", r1="100", r2="22", rc="2.2",
            re="1", beta="100", vbe="0.70",
        )
        self.sim_form = dict(
            mode="divider",
            sp_vcc="12", sp_r1="100", sp_r2="22", sp_rc="2.2", sp_re="1",
            sp_rl="10", sp_cin="10", sp_cout="10", sp_amp="10", sp_freq="1000",
            analysis="dc",
        )

    def _split(self, body):
        return body.split('id="results"', 1)

    def test_calculator_result_is_inside_unified_results_section(self):
        body = self.client.post("/calculate", data=self.dc).get_data(as_text=True)

        before, after = self._split(body)
        self.assertNotIn("DC Bias Results", before)
        self.assertIn("DC Bias Results", after)

    def test_simulator_form_carries_calculator_values(self):
        body = self.client.get("/").get_data(as_text=True)
        form = body.split('id="sim-form"', 1)[1]

        for key in ("vcc", "r1", "r2", "rc", "re", "beta", "vbe"):
            self.assertIn(f'name="{key}"', form)

    def test_dc_run_shows_calculator_and_spice_in_one_section(self):
        fake_result = {
            "analysis": "dc",
            "analysis_label": "DC Operating Point",
            "command": ".op",
            "engine": "ngspice 41 · Q2N2222",
            "model": "Q2N2222",
            "model_source": "test card",
            "started_at": "2026-11-24T00:00:00+00:00",
            "elapsed_s": 0.01,
            "run_dir": "/tmp/run",
            "netlist": "* netlist",
            "log_tail": "No. of Data Rows : 1",
            "warnings": [],
            "params": {
                "vcc": 12.0, "r1": 100_000.0, "r2": 22_000.0,
                "rc": 2_200.0, "re": 1_000.0,
            },
            "data": {
                "vb": 2.0, "ve": 1.3, "vc": 9.0, "vce": 7.7, "vbe": 0.7,
                "ic": 1.3e-3, "ib": 7e-6, "ie": 1.3e-3, "region": "active",
            },
        }
        data = dict(self.sim_form, **self.dc)
        with mock.patch("app.spice_engine.simulate", return_value=fake_result):
            body = self.client.post("/simulate", data=data).get_data(as_text=True)

        before, after = self._split(body)
        self.assertNotIn("SPICE (ngspice)", before)
        self.assertIn("DC Bias Results", after)
        self.assertIn("SPICE (ngspice)", after)


class TestInvalidInput(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.valid = dict(
            mode="divider",
            vcc="12",
            r1="100",
            r2="22",
            rc="2.2",
            re="1",
            beta="100",
            vbe="0.70",
        )

    def test_zero_vcc_shows_error(self):
        res = self.client.post("/calculate", data=dict(self.valid, vcc="0"))

        self.assertEqual(res.status_code, 200)
        self.assertIn("ข้อผิดพลาด", res.get_data(as_text=True))

    def test_non_numeric_shows_error(self):
        res = self.client.post("/calculate", data=dict(self.valid, vcc="abc"))

        self.assertEqual(res.status_code, 200)
        self.assertIn("ข้อผิดพลาด", res.get_data(as_text=True))

    def test_missing_field_shows_error(self):
        data = {k: v for k, v in self.valid.items() if k != "r1"}

        res = self.client.post("/calculate", data=data)

        self.assertEqual(res.status_code, 200)
        self.assertIn("ข้อผิดพลาด", res.get_data(as_text=True))


class TestDisplayAndLabels(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.valid = dict(
            mode="divider",
            vcc="12",
            r1="100",
            r2="22",
            rc="2.2",
            re="1",
            beta="100",
            vbe="0.70",
        )

    def test_form_labels_and_button_are_thai(self):
        body = self.client.get("/").get_data(as_text=True)
        for text in ("แรงดันไฟเลี้ยง", "ตัวต้านทานขา Base", "คำนวณ DC Bias"):
            self.assertIn(text, body)

    def test_region_is_shown_in_thai(self):
        res = self.client.post("/calculate", data=self.valid)
        self.assertIn("Active (ทำงานปกติ)", res.get_data(as_text=True))

    def test_warning_block_reaches_page(self):
        res = self.client.post("/calculate", data=dict(self.valid, rc="47"))
        body = res.get_data(as_text=True)
        self.assertIn("alert warning", body)
        self.assertIn("Saturation", body)

    def test_ib_displayed_in_microamps(self):
        res = self.client.post("/calculate", data=self.valid)
        self.assertIn("12.299", res.get_data(as_text=True))

    def test_vce_cell_has_value_and_unit(self):
        res = self.client.post("/calculate", data=self.valid)
        self.assertRegex(
            res.get_data(as_text=True), r"<th>VCE</th><td>8\.052 V</td>"
        )


class TestModeSelection(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index_offers_all_three_modes(self):
        body = self.client.get("/").get_data(as_text=True)

        self.assertIn('name="mode"', body)
        for label in ("Voltage Divider Bias", "Fixed Bias", "Emitter Bias"):
            self.assertIn(label, body)

    def test_fixed_mode_shows_rb_and_hides_divider_fields(self):
        body = self.client.get("/?mode=fixed").get_data(as_text=True)

        self.assertIn('name="rb"', body)
        self.assertNotIn('name="r1"', body)
        self.assertNotIn('name="r2"', body)

    def test_emitter_mode_shows_rb_and_re(self):
        body = self.client.get("/?mode=emitter").get_data(as_text=True)

        self.assertIn('name="rb"', body)
        self.assertIn('name="re"', body)
        self.assertNotIn('name="r1"', body)

    def test_unknown_mode_get_shows_error(self):
        res = self.client.get("/?mode=bogus")

        self.assertIn("ไม่รู้จักโหมด", res.get_data(as_text=True))


class TestFixedMode(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.data = dict(
            mode="fixed", vcc="12", rc="2.2", beta="100", vbe="0.70", rb="1000"
        )

    def test_a2_operating_point_and_mode_label(self):
        body = self.client.post("/calculate", data=self.data).get_data(as_text=True)

        self.assertIn("1.130", body)  # IC in mA
        self.assertIn("9.514", body)  # VCE in V
        self.assertIn("Fixed Bias", body)

    def test_zero_rb_shows_thai_error_without_stale_result(self):
        res = self.client.post("/calculate", data=dict(self.data, rb="0"))
        body = res.get_data(as_text=True)

        self.assertIn("ข้อผิดพลาด", body)
        self.assertIn("RB", body)
        self.assertNotIn("DC Bias Results", body)

    def test_unused_fields_are_not_required(self):
        res = self.client.post("/calculate", data=self.data)

        self.assertNotIn("ข้อผิดพลาด", res.get_data(as_text=True))

    def test_junk_in_unused_fields_is_ignored(self):
        res = self.client.post(
            "/calculate", data=dict(self.data, r1="abc", r2="xyz", re="")
        )

        self.assertNotIn("ข้อผิดพลาด", res.get_data(as_text=True))


class TestEmitterMode(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.data = dict(
            mode="emitter",
            vcc="12",
            rc="2.2",
            beta="100",
            vbe="0.70",
            rb="1000",
            re="1",
        )

    def test_a3_operating_point(self):
        body = self.client.post("/calculate", data=self.data).get_data(as_text=True)

        self.assertIn("1.026", body)  # IC in mA
        self.assertIn("8.705", body)  # VCE in V
        self.assertIn("Emitter Bias", body)

    def test_a4_larger_re_lowers_ic(self):
        body = self.client.post(
            "/calculate", data=dict(self.data, re="2")
        ).get_data(as_text=True)

        self.assertIn("0.940", body)  # IC in mA
        self.assertIn("8.033", body)  # VCE in V


class TestModeValidation(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.divider_values = dict(
            vcc="12", r1="100", r2="22", rc="2.2", re="1", beta="100", vbe="0.70"
        )

    def test_missing_mode_is_rejected(self):
        res = self.client.post("/calculate", data=self.divider_values)

        self.assertIn("ไม่รู้จักโหมด", res.get_data(as_text=True))

    def test_unknown_mode_is_not_treated_as_divider(self):
        res = self.client.post(
            "/calculate", data=dict(self.divider_values, mode="weird")
        )
        body = res.get_data(as_text=True)

        self.assertIn("ไม่รู้จักโหมด", body)
        self.assertNotIn("DC Bias Results", body)


if __name__ == "__main__":
    unittest.main()
