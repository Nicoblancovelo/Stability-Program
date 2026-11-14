@echo off
setlocal

cd /d "%~dp0"

call venv\Scripts\activate

powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1',8501); $c.Close(); exit 0 } catch { exit 1 }"
if %ERRORLEVEL%==0 (
  start "" "http://localhost:8501"
  exit /b 0
)

start "" /B python -m streamlit run app.py --server.port 8501 --server.headless true

for /l %%i in (1,1,40) do (
  powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1',8501); $c.Close(); exit 0 } catch { exit 1 }"
  if %ERRORLEVEL%==0 goto :OPEN
  timeout /t 1 >nul
)

:OPEN
start "" "http://localhost:8501"
exit /b 0