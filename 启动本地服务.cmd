@echo off
rem ============================================================
rem  OCR tool launcher - serves the html over local http
rem  Chrome/Edge restrict file:// pages (workers/blob blocked),
rem  so double-clicking the html directly hurts pdf.js/Tesseract.
rem  Usage: put this file, the .ps1 server and the html in one folder,
rem  then double-click. Works with Python or plain PowerShell.
rem  (This file is kept pure ASCII on purpose: cmd.exe decodes batch
rem   files with the console code page, so literal non-ASCII here would
rem   break on non-Chinese Windows.)
rem
rem  v2.2: on dual-GPU laptops the browser GPU process defaults to
rem  the integrated GPU, so WebGPU (and the OCR engine) runs on the
rem  slow iGPU. We now launch Chrome/Edge with
rem  --force_high_performance_gpu so WebGPU uses the discrete GPU.
rem ============================================================
cd /d "%~dp0"
set PORT=18010
set PAGE=
rem Pick the tool html: it is by far the largest .html in this folder (~44 MB),
rem so a stray readme.html saved next to it cannot be picked by mistake.
for %%f in ("%~dp0*.html") do if %%~zf GTR 10000000 set "PAGE=%%~nxf"
if not defined PAGE (
  echo [ERROR] No tool html found in this folder.
  echo Put this launcher next to the html file (the ~44 MB one), then run again.
  pause
  exit /b 1
)
where python >nul 2>nul
if %errorlevel%==0 (
  echo Starting local server via Python on port %PORT% ...
  start "" /min cmd /c "cd /d %~dp0 && python -m http.server %PORT% --bind 127.0.0.1"
  timeout /t 2 /nobreak >nul
) else (
  rem No Python: fall back to the bundled PowerShell server. It is found by
  rem wildcard instead of a literal name, so this file stays pure ASCII.
  set "PS1="
  for %%s in ("%~dp0*.ps1") do if not defined PS1 set "PS1=%%~fs"
  if not defined PS1 (
    echo [ERROR] Python not found and no .ps1 server script beside this file.
    pause
    exit /b 1
  )
  echo Python not found - starting the PowerShell server on port %PORT% ...
  echo Close this window to stop the server.
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Port %PORT% -Page "%PAGE%"
  pause
  exit /b 0
)

rem --- pick a Chromium browser and force the discrete GPU ---
set "BROWSER="
for %%p in (
  "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  "%LocalAppData%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
) do if not defined BROWSER if exist %%p set "BROWSER=%%~p"

if defined BROWSER (
  echo Launching with high-performance GPU: %BROWSER%
  start "" "%BROWSER%" --force_high_performance_gpu "http://127.0.0.1:%PORT%/%PAGE%"
) else (
  echo Chrome/Edge not found - opening with the default browser.
  echo NOTE: WebGPU may then run on the integrated GPU.
  start "" "http://127.0.0.1:%PORT%/%PAGE%"
)
echo.
echo Server is running in the background (minimized python window).
echo To stop it later: close that minimized python window.
exit /b 0
