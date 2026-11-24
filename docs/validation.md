# Validation — BJT DC Bias Web App

วันที่ตรวจ: 2026-11-10

## 1. ค่าอ้างอิงทางวิศวกรรม vs ค่าที่เว็บแสดง

ข้อมูลทดลองเริ่มต้น: `VCC = 12 V, R1 = 100 kΩ, R2 = 22 kΩ, RC = 2.2 kΩ, RE = 1 kΩ, β = 100, VBE = 0.70 V`

ค่าอ้างอิงคำนวณด้วยมือจากสมการ Forward-Active ใน `docs/design-note.md` ข้อ 8

| ปริมาณ | ค่าคำนวณด้วยมือ | ค่าที่เว็บแสดง | ตรงกัน |
|---|---|---|---|
| VB | 1.942167 V | 1.942 V | ✅ |
| VE | 1.242167 V | 1.242 V | ✅ |
| VC | 9.294290 V | 9.294 V | ✅ |
| VCE | 8.052123 V | 8.052 V | ✅ |
| IC | 1.229868 mA | 1.230 mA | ✅ |
| IE | 1.242167 mA | 1.242 mA | ✅ |
| IB | 12.29868 µA | 12.299 µA | ✅ |
| Operating Region | active | active | ✅ |

## 2. การทดสอบอัตโนมัติ

คำสั่ง: `python -m unittest discover -s tests -v`

```
Ran 39 tests in 0.043s
OK
```

| ไฟล์ | จำนวน | ครอบคลุม |
|---|---|---|
| `tests/test_dc_bias.py` | 17 | ค่าอ้างอิงทั้งสามโหมด, validation, region (active/cutoff/saturation), การแปลงค่าที่ไม่ใช่ตัวเลข/NaN/Inf, RE ที่มากขึ้นต้องลด IC |
| `tests/test_web.py` | 22 | GET ฟอร์ม, POST คำนวณทั้งสามโหมด, input ผิด, โหมดที่ไม่รู้จัก, ช่องที่ไม่ใช้ไม่ถูกบังคับ, ป้ายภาษาไทย, region ภาษาไทย, warning block, IB หน่วย µA, รูปแบบเซลล์ VCE |

## 3. การทดสอบผ่าน HTTP จริง (ไม่ใช่ test client)

รัน `python -m flask --app app run --port 5000` แล้วยิง request จริง

| การทดสอบ | ผล |
|---|---|
| `GET /` | 200 และพบ `name="vcc"` |
| `POST /calculate` (ค่าอ้างอิง) | 200, พบ `8.052` (VCE) และ `1.230` (IC) |
| `POST /calculate` (VCC = 0) | 200 และแสดงข้อความ "ข้อผิดพลาด" |

## 4. กรณีอยู่นอก Forward-Active

| กรณี | อินพุต | ผลที่ได้ |
|---|---|---|
| Cutoff | `R2 = 1 kΩ` (VTH ≈ 0.119 V < VBE) | IC = 0, VCE = 12 V, region = cutoff, มี warning |
| Saturation | `RC = 47 kΩ` (VCE < 0.2 V) | region = saturation, มี warning ว่าใช้ค่าจาก Forward-Active ไม่ได้ |

หมายเหตุ: ค่าที่แสดงในสองกรณีนี้มาจากสมการ Forward-Active เช่นเดิม ตามแนวทาง A
ของ design note — ตัวเลขใช้ดูพฤติกรรมของสมการเท่านั้น ไม่ใช่ค่าที่เชื่อถือได้

## 5. หลักฐานประกอบการส่ง

รันเว็บด้วย `python -m flask --app app run --port 5000` แล้วจับภาพหน้าจอจริง
จากเบราว์เซอร์ (ขนาดเต็มหน้า)

| ไฟล์ | เนื้อหา |
|---|---|
| `docs/screenshots/01-form.jpeg` | หน้าแรก แสดงฟอร์ม 7 ช่อง พร้อมคำอธิบายภาษาไทยและปุ่ม "คำนวณ DC Bias" |
| `docs/screenshots/02-result.jpeg` | ผลลัพธ์ค่าอ้างอิง: VB 1.942 V · VE 1.242 V · VC 9.294 V · VCE 8.052 V · IC 1.230 mA · IE 1.242 mA · IB 12.299 µA · Active (ทำงานปกติ) |
| `docs/screenshots/03-invalid-input.jpeg` | กรอก VCC = 0 → แถบ error "ข้อผิดพลาด: VCC ต้องมากกว่า 0 V" (HTTP 200) |
| `docs/screenshots/04-saturation-warning.jpeg` | ตั้ง RC = 47 kΩ → region = Saturation (อิ่มตัว) พร้อม warning |

`docs/test-log.txt` เก็บผลรัน `python -m unittest discover -s tests -v`
จากเครื่องที่พัฒนา (39 tests, OK) เพื่อใช้อ้างอิงคู่กับตารางข้อ 2

## 6. Lab 03 — ตารางตรวจรับ A1–A5

ใช้ร่วมกันทุกกรณี: `VCC = 12 V, RC = 2.2 kΩ, β = 100, VBE = 0.70 V`
เกณฑ์: IC คลาดเคลื่อน ≤ 0.01 mA · VCE ≤ 0.02 V เทียบกับค่าอ้างอิงที่ยังไม่ปัดเศษ

ค่าอ้างอิงของโหมดใหม่คำนวณด้วยมือ (ไม่ใช้ผลจากโปรแกรม):

- **A2 Fixed Bias** (RB = 1 MΩ): `IB = (12 − 0.7)/1,000,000 = 11.300 µA` ·
  `IC = 100 × IB = 1.130 mA` · `IE = 101 × IB = 1.141 mA` · `VE = 0 V` ·
  `VB = 0.700 V` · `VC = 12 − 1.130 mA × 2.2 kΩ = 9.514 V` · `VCE = 9.514 V`
- **A3 Emitter Bias** (RB = 1 MΩ, RE = 1 kΩ): `IB = 11.3/(1,000,000 + 101 × 1,000) = 10.263 µA` ·
  `IC = 1.0263 mA` · `VE = 101 × IB × 1 kΩ = 1.0366 V` · `VB = 1.7366 V` ·
  `VC = 12 − 1.0263 mA × 2.2 kΩ = 9.7421 V` · `VCE = 8.7054 V`
- **A4 Emitter Bias** (เหมือน A3 แต่ RE = 2 kΩ): `IB = 11.3/1,202,000 = 9.401 µA` ·
  `IC = 0.9401 mA` (ลดลงจาก A3) · `VCE = 8.0328 V`

| กรณี | โหมดและอินพุต | คาดหมายก่อนรัน | เห็นจริง | วิธีตรวจ | สถานะ |
|---|---|---|---|---|---|
| A1 | Divider · R1 = 100 kΩ, R2 = 22 kΩ, RE = 1 kΩ | ผลเดิมของ Lab 02: IC 1.230 mA · VCE 8.052 V | IC 1.230 mA · VCE 8.052 V · VB 1.942 V · VE 1.242 V · VC 9.294 V · Active | OpenCode Browser | PASS |
| A2 | Fixed · RB = 1 MΩ (1000 kΩ) | IC 1.130 mA · VCE 9.514 V (ไม่ต้องกรอก RE) | IC 1.130 mA · VCE 9.514 V · VB 0.700 V · VE 0.000 V · IB 11.300 µA | OpenCode Browser | PASS |
| A3 | Emitter · RB = 1 MΩ, RE = 1 kΩ | IC 1.0263 mA · VCE 8.7054 V | IC 1.026 mA · VCE 8.705 V · VE 1.037 V · IB 10.263 µA | OpenCode Browser | PASS |
| A4 | Emitter · เหมือน A3 แต่ RE = 2 kΩ | ทำนาย: IC ลดลง เพราะ RE มากขึ้นทำให้ IB = (VCC−VBE)/(RB+(β+1)RE) ลดลง | IC 0.940 mA (ลดจาก 1.026 mA) · VCE 8.033 V · VE 1.899 V | OpenCode Browser | PASS |
| A5 | Fixed · RB = 0 | มีข้อความให้แก้ RB เว็บไม่ล่ม และไม่แสดงผลรอบก่อน | "โหมด: Fixed Bias — ข้อผิดพลาด: ค่าความต้านทาน RB ต้องมากกว่า 0 Ω" ไม่มีตารางผลลัพธ์ | OpenCode Browser | PASS |

หมายเหตุวิธีตรวจ: ตรวจผ่านเบราว์เซอร์ของ OpenCode Desktop (แท็บ Review) ด้วยการเลือกโหมด
กรอกค่าในฟอร์มจริง แล้วกดปุ่ม "คำนวณ DC Bias" ไม่ได้ใช้ `curl` หรืออ่านโค้ดแทน

## 7. หลักฐาน Lab 03

| ไฟล์ | เนื้อหา |
|---|---|
| `docs/screenshots/05-fixed-mode.png` | A2 · Fixed Bias, RB = 1000 kΩ → IC 1.130 mA · VCE 9.514 V · โหมดระบุบนหัวตารางผล |
| `docs/screenshots/06-invalid-rb.png` | A5 · Fixed Bias, RB = 0 → error ภาษาไทย ระบุโหมด และไม่มีตารางผลค้างจากรอบก่อน |

## 8. Lab 04 — Browser acceptance B1–B8

วันที่ตรวจ: 2026-11-24  
แอปทดสอบ: `http://127.0.0.1:5001/` (Flask dev server, local — ใช้พอร์ต 5001 เพราะ LAB3 ใช้ 5000)  
เครื่องมือเบราว์เซอร์: **OpenCode browser tool** (`tools.browser.*` ใน Code Mode) — **ไม่ใช่ Playwright MCP** เพราะไม่มี Playwright MCP ปรากฏในรายการ tool/MCP resource ของเซสชันนี้ จึงบันทึกว่า **Playwright MCP NOT RUN** ตามเงื่อนไขของใบงาน และใช้ OpenCode browser tool ตรวจจริง (navigate, snapshot, select/fill, click, evaluate, wait, screenshot)  
Engine จริง: **ngspice 41** · Model **Q2N2222** (Philips parameters, BF=200) · เรียกผ่าน `spice_engine.py` ด้วย subprocess (ไม่มี `shell=True`)  
Harness ชั่วคราว: `static/_b1_modes.html` และ `static/_mobile_preview.html` ถูกเสิร์ฟจาก Flask เพื่อฝังผลจริงจาก `/calculate` และ `/simulate` ใน iframe; เป็นตัวช่วยจับภาพ **ไม่ได้ commit (เพิ่มใน `.gitignore`)**

| Case | Method | Input | Expected / Reference | Observed | Evidence | Status |
|---|---|---|---|---|---|---|
| B1 · Regression | เปิด `/static/_b1_modes.html` แล้วตรวจ 3 iframe ที่ POST `/calculate` จริง; อ่าน `.mode-tag`, IC, VCE ด้วย DOM evaluate | Divider: 12 V / 2.2 kΩ / β100 / 0.70 V / R1 100 kΩ / R2 22 kΩ / RE 1 kΩ · Fixed: RB 1 MΩ · Emitter: RB 1 MΩ + RE 1 kΩ | Divider IC≈1.230 mA, VCE≈8.052 V · Fixed IC≈1.130 mA, VCE≈9.514 V · Emitter IC≈1.026 mA, VCE≈8.705 V · ทุกโหมด Active | Divider **1.230 mA / 8.052 V** · Fixed **1.130 mA / 9.514 V** · Emitter **1.026 mA / 8.705 V** · ตรงค่าอ้างอิง Lab 03 ทุกตัว | `docs/captures/b1_regression_3modes.png`; อีกชุด `b1_divider.png`, `b1_fixed.png`, `b1_emitter.png` | PASS |
| B2 · DC SPICE | กด `.op · DC Operating Point` บนฟอร์ม CE reference; ตรวจ status, provenance, netlist/run log ใน `<details>` | CE defaults: VCC 12 V, R1 100 kΩ, R2 22 kΩ, RC 2.2 kΩ, RE 1 kΩ, RL 10 kΩ, Cin/Cout 10 µF | `.op` สำเร็จ, แสดง VB/VE/VC/VCE/VBE/IC/IE/IB + region, engine/model, run dir, netlist/log จริง | Success · `ngspice 41 · Q2N2222` · VB **2.047 V**, VE **1.385 V**, VC **8.967 V**, VCE **7.582 V**, VBE 0.662 V, IC **1.379 mA**, IE 1.385 mA, IB 6.476 µA, Active · run dir `20261124T104300_dc_kc9tvao4` | `docs/captures/b2_dc.png` (มี netlist/log แนบในหน้า) | PASS |
| B3 · Change RE | เปลี่ยนเฉพาะ `sp_re` 1 → 2 kΩ แล้วรัน `.op` ใหม่ เปรียบเทียบกับ B2 | RE = 2 kΩ (ตัวอื่นเท่าเดิม) | Operating point ต้องเปลี่ยนและมาจากรันใหม่ ไม่ใช่ค่าค้าง | IC **1.379 → 0.726 mA**, VCE **7.582 → 8.945 V**, VB 2.047 → 2.103 V, VE 1.385 → 1.458 V, IB 6.476 → 3.359 µA · run dir ใหม่ `20261124T104422_dc_jilfk5ch` | `docs/captures/b2_dc.png`, `docs/captures/b3_re2_dc.png` | PASS |
| B4 · AC | รัน `.ac dec` แล้วตรวจ metrics, แกน, legend และจำนวนจุดจาก SVG polyline | Default CE, sweep 0.1 Hz–100 MHz, 20 pts/dec | Bode plot แกน Frequency (log Hz) / Gain (dB) / Phase (deg); midband, fL, fH, bandwidth จากข้อมูลรันจริง | Midband **1.760× (4.91 dB)**, phase **−180.0° (inverting)**, fL **1.78 Hz**, fH **63.1 MHz**, Bandwidth **63.1 MHz** (= fH − fL), 181 จุด · SVG 2 polyline คนละ 181 จุด · run dir `20261124T104423_ac_x5sk6w_p` | `docs/captures/b4_ac_bode.png` (metrics + netlist/log), `docs/captures/b4_ac_chart.png` (Bode plot เต็ม) | PASS |
| B5 · Transient | รัน `.tran` ที่ Vin **10 mV peak**, 1 kHz; ตรวจ Vin/Vout ตามเวลา, ทิศทางเฟส, จำนวนจุด SVG | Vin 10.00 mV peak, 1 kHz, 0–5 ms | เห็น Vin/Vout vs time, Vout กลับเฟส, gain/waveform มาจากรันจริง มีหน่วยเวลา/แรงดัน | Vin peak **10.00 mV**, Vout peak **17.60 mV**, gain **1.760×**, เฟส **กลับเฟส 180°**, ช่วง **0–5.00 ms**, 1,008 จุด · SVG 2 polyline คนละ 1,008 จุด · run dir `20261124T104423_tran_pipxh8z5` | `docs/captures/b5_tran.png` (metrics), `docs/captures/b5_tran_chart.png` (waveform เต็ม) | PASS |
| B6 · Change Source | รัน `.tran` ซ้ำโดยเปลี่ยนเฉพาะ amplitude 10 → 20 mV peak | Vin 20.00 mV peak, 1 kHz (ตัวอื่นเท่าเดิม) | Waveform/metrics ต้องเปลี่ยนตามอินพุต ไม่ใช่กราฟ hard-code | Vin peak **20.00 mV**, Vout peak **35.20 mV**, gain **1.760×**, 0–5.00 ms, 1,008 จุด · Vout เพิ่มจาก 17.60 → 35.20 mV เทียบ B5 · run dir ใหม่ `20261124T104423_tran_o6zlv0rb` | `docs/captures/b5_tran_chart.png` (ก่อน), `docs/captures/b6_amp20_chart.png` (หลัง) + `b5_tran.png`, `b6_amp20.png` | PASS |
| B7 · Invalid / Fail | ตั้ง `sp_re = 0` แล้วกดรัน DC | RE = 0 kΩ (นอกช่วง 0.01–100 kΩ) | ต้องแจ้ง error ภาษาไทย ไม่ล่ม และไม่โชว์ผลสำเร็จ/กราฟเก่า | `Simulation Error` · **"ข้อมูลไม่ถูกต้อง: ค่า RE ต้องอยู่ระหว่าง 0.01–100 kΩ ไม่มีการแสดงกราฟหรือตัวเลขจากรอบก่อนหน้า เพราะรอบนี้ไม่สำเร็จ"** · ไม่มี `.sim-results`, ไม่มี SVG chart | `docs/captures/b7_error.png` | PASS |
| B8 · UI | เปิด `/static/_mobile_preview.html` ในแท็บเดียว: กดปุ่ม **Desktop full-width** (DC `.op`) หรือ **Phone 390px** (AC `.ac`) เพื่อสลับ viewport แบบเต็มจอ; ทั้งคู่ POST `/simulate` จริง | Desktop full-width + Phone 390 px, ทั้งคู่ POST `/simulate` จริง | อ่านง่าย กราฟ/หน่วย/ปุ่มไม่ถูกตัดจนใช้งานไม่ได้; เปลี่ยน analysis ได้ | Desktop แสดงตาราง DC + status `ngspice 41 · Q2N2222` ครบ; 390 px แสดง AC metrics + Bode plot ใน `chart-scroll` (เลื่อนแนวนอนได้) ไม่มี overflow ตัดหัวตาราง | `docs/captures/b8_desktop_full.png` (desktop เต็มจอ), `docs/captures/b8_phone_full.png` / `b8_mobile_chart.png` (390px เต็มจอ); กราฟเดสก์ทอป `docs/captures/b4_ac_chart.png` | PASS (มีข้อจำกัด: ไม่ใช่ device emulation แบบ DevTools) |

### หมายเหตุความซื่อสัตย์ของการทดสอบ

- **Playwright MCP**: **NOT RUN** / ไม่ปรากฏในสภาพแวดล้อมนี้ — ไม่ได้อ้างว่าเป็นผล Playwright MCP
- **Browser tool ที่ใช้จริง**: OpenCode `tools.browser.*` (navigate, snapshot, select/fill, click, evaluate, wait, screenshot) ผ่าน Flask `http://127.0.0.1:5001/`
- **Viewport มือถือ**: browser tool ไม่มี device-emulation API โดยตรง จึงใช้ harness ที่เสิร์ฟจาก Flask สลับ iframe ระหว่าง full-width กับ 390 px แบบเต็มจอ และ POST `/simulate` จริง แล้วจับภาพจริง; ผ่านสำหรับตรวจ layout พื้นฐาน แต่ไม่เทียบเท่า Chrome DevTools device emulation
- **B1 harness**: 3 iframe POST `/calculate` จริง (ไม่ใช่ค่าจำลองในหน้า harness) ค่าอ่านจาก DOM ของแต่ละ frame
- **Chart provenance**: ตัวเลข metrics และพิกัด polyline อ่านจาก DOM/SVG ที่ render จาก response จริง; SVG ถูกสร้าง server-side ใน `charts.py` จาก ngspice output ที่ parse ใน `spice_engine.py` (ไม่มี hard-coded waveform)
- **ข้อจำกัด engine**: ต้องติดตั้ง ngspice ให้ Flask พบ (หรือใช้ชุด portable ใน `tools/ngspice` ซึ่งไม่ได้ commit) ถ้าไม่พบ engine ระบบต้องแสดง error ไม่ใช่ผลสำเร็จปลอม
