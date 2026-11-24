# BJT DC Bias & CE Amplifier Web App

เว็บแอปพลิเคชันสำหรับวิชา ENG29 2121 พัฒนาด้วย Python + Flask  
ต่อยอดจาก Lab 02–03 (DC Bias เชิงวิเคราะห์ 3 โหมด) มาเป็น **Lab 04 CE Amplifier Simulator** ที่รัน ngspice จริง

## สิ่งที่แอปรองรับ

- **DC Bias Calculator (Analytical, Python)**: Fixed / Emitter / Voltage Divider — คำนวณสดจากสมการใน `dc_bias.py`
- **CE Amplifier Simulator (ngspice จริง)**: วงจรอ้างอิง CE Voltage Divider เดียว
  - `.op` DC Operating Point
  - `.ac` Bode plot (gain/phase, fL/fH/bandwidth)
  - `.tran` Transient waveform (Vin/Vout, peak, gain, inversion)
- ผล SPICE และผล Analytical แสดงร่วมใน section “ผลลัพธ์รวม” (ฟอร์มยังแยกกัน; ค่า DC Bias ถูกส่งเป็น hidden fields ตอนรัน simulator) พร้อม engine/model/run dir/netlist/log tail
- กราฟ SVG สร้างจากข้อมูลรันจริงเท่านั้น (ไม่มี hard-coded waveform)

## โหมดที่รองรับ

| โหมด | อินพุตเพิ่ม | ตัวต้านทานในวงจร | ฟังก์ชัน |
|---|---|---|---|
| Voltage Divider Bias | R1, R2, RE | R1 จาก VCC ไป Base · R2 จาก Base ลงกราวด์ · RE จาก Emitter ลงกราวด์ | `solve()` |
| Fixed Bias | RB | RB จาก VCC ไป Base · Emitter ลงกราวด์โดยตรง | `fixed_bias()` |
| Emitter Bias | RB, RE | RB จาก VCC ไป Base · RE จาก Emitter ลงกราวด์ | `emitter_bias()` |

เลือกโหมดจาก dropdown แล้วกด "เปลี่ยนโหมด" — ฟอร์มจะแสดงเฉพาะช่องที่โหมดนั้นใช้
(ทำงานฝั่ง Flask ไม่ต้องใช้ JavaScript)

## สมการ

| โหมด | IB |
|---|---|
| Fixed | `(VCC − VBE) / RB` |
| Emitter | `(VCC − VBE) / [RB + (β+1)·RE]` |
| Voltage Divider | `(VTH − VBE) / [RTH + (β+1)·RE]` โดย `VTH = VCC·R2/(R1+R2)`, `RTH = R1·R2/(R1+R2)` |

จาก IB: `IC = β·IB`, `IE = (β+1)·IB`, `VE = IE·RE` (Fixed → `VE = 0`),
`VB = VE + VBE`, `VC = VCC − IC·RC`, `VCE = VC − VE`

## Requirements

- Python 3.12+ (ทดสอบด้วย Python 3.12.10)
- Flask 3.1+ (`requirements.txt`)
- **ngspice** (จำเป็นสำหรับ Lab 04 simulator)

## ติดตั้ง ngspice

แอปจะค้นหา ngspice ตามลำดับ: `NGSPICE_BIN` env var → `tools/ngspice/Spice64/bin/ngspice.exe` → `ngspice` ใน PATH

ตัวอย่าง Windows (portable):
1. ดาวน์โหลด ngspice Windows zip จาก https://ngspice.sourceforge.io/download.html
2. แตกไฟล์ไว้ที่ `tools/ngspice/` ภายในโปรเจกต์ (ไม่ commit โฟลเดอร์นี้)
3. ตรวจสอบ: `tools\ngspice\Spice64\bin\ngspice.exe -v`

หรือถ้าติดตั้งในระบบแล้ว ให้ตั้งค่า:
```powershell
$env:NGSPICE_BIN="C:\path\to\ngspice.exe"
```

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS
python -m pip install -r requirements.txt
```

## Run

```powershell
python -m flask --app app run --debug --port 5001
```

เปิดเบราว์เซอร์ที่ <http://127.0.0.1:5001/>
(ถ้า LAB3 ยังเปิดอยู่ที่พอร์ต 5000 ให้ใช้ 5001 สำหรับ Lab 04)

> ต้องเปิดผ่าน Flask Server เท่านั้น การ double-click เปิด `templates/index.html`
> ด้วย `file://` จะไม่ได้ผล เพราะไม่มี Python คำนวณและไม่มี HTTP request

## Tests

```powershell
python -m unittest discover -s tests -v
```

- `tests/test_dc_bias.py` — สมการ DC bias ทั้งสามโหมด, validation, region
- `tests/test_web.py` — HTTP routes ของ DC bias ผ่าน Flask test client
- `tests/test_simulator.py` — แปลงหน่วย/validation, netlist, parser wrdata, route `/simulate`, และ real ngspice integration (skip ถ้าไม่พบ ngspice)

ผลรันล่าสุด: **68 tests OK** (รวม real ngspice integration บนเครื่องพัฒนา)

## BJT model (Lab 04 SPICE)

ทุก netlist ฝังโมเดล NPN ชื่อ `Q2N2222` โดยตรง (ไม่พึ่ง library ภายนอก):

```spice
.model Q2N2222 NPN (IS=1E-14 VAF=100 BF=200 IKF=0.3 XTB=1.5 BR=3
+ CJC=8E-12 CJE=25E-12 TR=100E-9 TF=400E-12 ITF=1 VTF=2 XTF=3 RB=10
+ RC=.3 RE=.2)
```

พารามิเตอร์นี้คัดลอกจาก standard ngspice example card (Philips parameters) ที่ใช้กับ 2N2222 เพื่อให้ได้พฤติกรรมทรานซิสเตอร์ NPN สมจริงในระดับการเรียน; ไม่ใช่การรับประกันว่าเท่าชิปจริงทุกตัว. ตรวจจริงด้วย **ngspice 41** ค่า Analytical reference ในหน้า DC SPICE ใช้ `β=100, VBE=0.70 V` (ตามโจทย์ Lab 3) จึงต่างจาก SPICE ได้และแสดงแยกคอลัมน์ใน section ผลลัพธ์รวมอย่างชัดเจน.

## ค่าตรวจรับ Lab 03 (regression)

| กรณี | โหมดและอินพุต | IC | VCE | สถานะ |
|---|---|---|---|---|
| A1 | Divider · R1 100 kΩ, R2 22 kΩ, RE 1 kΩ | 1.230 mA | 8.052 V | PASS |
| A2 | Fixed · RB 1 MΩ | 1.130 mA | 9.514 V | PASS |
| A3 | Emitter · RB 1 MΩ, RE 1 kΩ | 1.026 mA | 8.705 V | PASS |
| A4 | Emitter · RB 1 MΩ, RE 2 kΩ | 0.940 mA (ลดลง) | 8.033 V | PASS |
| A5 | Fixed · RB = 0 | error ภาษาไทย | — | PASS |

## ค่าตรวจรับ Lab 04 (B1–B8)

รายละเอียดเต็มใน `docs/validation.md` ข้อ 8. สรุป: B1–B8 **PASS** ด้วย OpenCode browser tool (Playwright MCP ไม่พร้อมใช้งาน จึงบันทึก NOT RUN สำหรับ Playwright MCP และใช้ browser tool จริงแทน พร้อมหลักฐาน screenshot ใน `docs/captures/`).

## Project structure

```
app.py                  Flask routes: DC bias + /simulate (ngspice)
dc_bias.py              สมการ DC bias เชิงวิเคราะห์ 3 โหมด + validation + region
spice_engine.py         Netlist builder, ngspice subprocess runner, wrdata parser
charts.py               Server-side SVG charts จากข้อมูลรันจริง
templates/index.html    UI: DC bias panel + CE simulator + unified results section
static/style.css        รูปแบบหน้าเว็บ
tests/                  unittest (dc_bias, web, simulator)
docs/                   validation, captures/screenshots, notes
tools/                  local ngspice portable (ไม่ commit)
```

## Assumptions & limitations

- DC bias analytical ใช้สมการ Forward-Active โดยประมาณ: β คงที่, VBE คงที่, ไม่คิด Early effect/อุณหภูมิ
- SPICE ใช้โมเดล Q2N2222 ที่ฝังใน netlist; ผลต่างจาก Analytical ได้และเป็นเรื่องคาดหมาย
- จุดวัด AC/Tran: Vin = `src` (ก่อน Cin), Vout = `out` (หลัง Cout คร่อม RL)
- ค่าตัด −3 dB หาได้เฉพาะเมื่ออยู่ในช่วง sweep; ถ้าไม่พบจะแสดง "ไม่พบในช่วง sweep" ไม่เดาค่า
- ขอบเขต Lab 04: CE voltage-divider reference circuit เดียว, ไม่มี drag-drop editor, ไม่มี free-form wiring, ไม่มี AC สำหรับ bias modes อื่น, ไม่มี FET/custom solver/animated overlay/public deploy

## ส่วนที่ AI ช่วยพัฒนา / นักศึกษาตรวจ (Lab 04)

- AI: วางสถาปัตยกรรม `spice_engine.py` / `charts.py` / web layer ตาม `AGENTS.md` และเขียน netlist builder + subprocess adapter + wrdata parser + SVG charts จากข้อมูลจริง
- AI: เพิ่ม `/simulate` route, UI ผลลัพธ์รวม, provenance/netlist/log, error ภาษาไทย และ tests (`test_simulator.py`, `test_web.py`) พร้อมรัน regression 68 tests OK
- AI: ตรวจ B1–B8 ด้วย OpenCode browser tool จริง บันทึกหลักฐานใน `docs/captures/` และระบุว่า Playwright MCP NOT RUN อย่างซื่อสัตย์
- นักศึกษา: ตรวจ netlist, ผล ngspice, การแปล gain/phase/cutoff, ความตรงของหลักฐาน และลองเปลี่ยนค่าแล้วดูกราฟเปลี่ยนจริงก่อนส่งงาน

## ลิงก์ส่งงาน

- GitHub (Lab 04): <https://github.com/Pormor1010/LAB4>
- Commit SHA ของงาน Lab 03: `9e43ed8` (feat(lab03): add fixed and emitter bias modes)
- Commit SHA ของโค้ด Lab 04: `224663e99ff544ae8af829711377122c25d0cc2c`

