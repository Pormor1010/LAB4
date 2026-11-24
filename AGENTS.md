# AGENTS.md — กติกาสำหรับ AI coding agent

โปรเจกต์: BJT DC Bias & CE Amplifier Web App (ENG29 2121 Lab 02–04)

## สถาปัตยกรรม

| ไฟล์ | หน้าที่ | ห้ามทำ |
|---|---|---|
| `dc_bias.py` | สมการ DC bias เชิงวิเคราะห์, validation, region detection | ห้าม import Flask, ห้ามรู้จัก HTTP หรือหน่วย kΩ |
| `spice_engine.py` | สร้าง netlist, เรียก ngspice ผ่าน subprocess, parse/validate ผลลัพธ์ | ห้ามใช้ `shell=True`, ห้าม hardcode trace/chart, ห้ามซ่อน error ของ ngspice |
| `charts.py` | สร้าง SVG chart จากข้อมูลรันจริงเท่านั้น | ห้ามมีข้อมูล waveform/sample hard-coded |
| `app.py` | HTTP route, แปลงหน่วย, จัดการ error, ส่งผลลัพธ์ให้ template | ห้ามมีสมการไฟฟ้า/สูตร SPICE เชิงวิเคราะห์ซ้ำซ้อนโดยไม่จำเป็น |
| `templates/index.html` | แสดงผลเท่านั้น | ห้ามคำนวณหรือมีสมการ |
| `tests/` | unittest | ห้ามแก้ Production code เพื่อให้ test ผ่านโดยไม่จำเป็น |

## กติกา

1. หน่วยภายใน `dc_bias.py` เป็น SI ทั้งหมด (V, Ω, A) — การแปลงหน่วย UI ทำที่ชั้น web/UI
2. ห้าม hardcode ผลลัพธ์ กราฟ หรือตัวเลขตัวอย่างใน template/JS; กราฟต้องมาจากข้อมูลรันจริง
3. เพิ่ม/แก้สมการเชิงวิเคราะห์ → ต้องมี test ใน `tests/test_dc_bias.py` ก่อน
4. เพิ่ม/แก้ route/web behavior → ต้องมี test ใน `tests/test_web.py` หรือไฟล์ test web ที่เกี่ยวข้อง
5. เพิ่ม/แก้ netlist parsing/SPICE adapter → ต้องมี test ใน `tests/test_simulator.py` หรือไฟล์ test simulator ที่เกี่ยวข้อง
6. รัน `python -m unittest discover -s tests -v` ให้เขียวก่อนทุกครั้งที่ commit
7. ห้าม commit `.venv/`, `.env`, `__pycache__/`, API key, `tools/`, `instance/runs/`
8. ข้อความ error/warning ที่ผู้ใช้เห็นต้องเป็นภาษาไทยและบอกสาเหตุ; ห้ามซ่อน error ของ ngspice
9. Lab 04 ขอบเขต: CE voltage-divider reference circuit + DC `.op` / AC `.ac` / Transient `.tran` ด้วย ngspice จริง และคง 3 โหมด DC bias เชิงวิเคราะห์เดิม
10. อยู่นอกขอบเขต: drag-drop editor, free-form wiring, AC สำหรับ bias mode อื่น, FET, custom SPICE solver, animated circuit overlay, public deploy

## คำสั่งที่ใช้บ่อย

```powershell
python -m unittest discover -s tests -v
python -m flask --app app run --debug
```
