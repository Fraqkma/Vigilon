## เริ่มระบบและเปิดใช้โมเดล

เตรียม .env และฐานข้อมูลจาก PowerShell ที่ root ของ repo:

.\scripts\setup.ps1
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.commands migrate
.\.venv\Scripts\python.exe -m app.commands bootstrap-admin

ติดตั้ง PyTorch build ที่ตรงกับ CPU/CUDA ของเครื่องก่อน แล้วติดตั้ง optional AI runtime:

.\.venv\Scripts\python.exe -m pip install -r requirements-ai.lock

เปิด API และ worker แยกกัน โดยตั้ง $env:PYTHONPATH = 'backend' ในแต่ละ terminal:

.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

.\.venv\Scripts\python.exe -m app.worker

ส่ง checkpoint ที่ได้รับอนุมัติไปยังตำแหน่งเหล่านี้ แล้วปรับ classes.json, scenario และ package metadata ให้ตรงกับ checkpoint:

- models/people_vehicle/weights/best.pt → C:\Users\server\Documents\GitHub\Vigilon\models\people_vehicle\weights\best.pt
- models/fire_smoke/weights/best.pt → C:\Users\server\Documents\GitHub\Vigilon\models\fire_smoke\weights\best.pt

ตรวจและสั่ง worker reload แยกสำหรับแต่ละโมดูล:

.\.venv\Scripts\python.exe -m app.commands validate-model people_vehicle --mode metadata
.\.venv\Scripts\python.exe -m app.commands validate-model people_vehicle --mode runtime
.\.venv\Scripts\python.exe -m app.commands reload-model people_vehicle

.\.venv\Scripts\python.exe -m app.commands validate-model fire_smoke --mode metadata
.\.venv\Scripts\python.exe -m app.commands validate-model fire_smoke --mode runtime
.\.venv\Scripts\python.exe -m app.commands reload-model fire_smoke

จากนั้นเลือกโมดูลใน Visor → AI Hub สำหรับ RTSP/RTSPS source ที่ตั้งค่าไว้ ส่วน FILE analysis สร้างและติดตามงานได้ใน AI Hub; CLI ก็ใช้ได้ เช่น .\.venv\Scripts\python.exe -m app.commands analyze-video --input entrance.mp4 --modules people_vehicle --output .data\analysis โดยไฟล์ต้องอยู่ใต้ VIGILON_MEDIA_DIR ค่าเริ่มต้นของ Compose mount models และ sample_data แบบ read-only

เอกสาร package และข้อจำกัดอยู่ที่ models/README.md (models/README.md), docs/AI_HUB.md (docs/AI_HUB.md) และ docs/IMPLEMENTATION_STATUS.md (docs/IMPLEMENTATION_STATUS.md) API ของ adapter อ้างอิงรูปแบบ detection results และ ByteTrack ตาม Ultralytics detection docs และ ByteTrack reference; ยังไม่ได้ยืนยัน runtime กับเวอร์ชันที่ pin ด้วย checkpoint จริง
