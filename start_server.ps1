$env:PYTHONIOENCODING = "utf-8"
Set-Location "D:\Projects\iptv"

$python = "C:\Users\suerwei\miniconda3\python.exe"
$code = "import uvicorn; from backend.main import app; uvicorn.run(app, host='127.0.0.1', port=8000)"

& $python -c $code
