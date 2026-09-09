@echo off
rem ============================================================
rem  Direct-open launcher - no local http server needed.
rem  Double-clicking the html also works (file:// was verified to
rem  run the GPU engine fine), but the browser then picks its own
rem  GPU, which on dual-GPU laptops is usually the integrated one.
rem  This script forces the discrete GPU via
rem  --force_high_performance_gpu so WebGPU/OCR runs on it.
rem ============================================================
cd /d "%~dp0"
set PAGE=
rem Pick the tool html: it is by far the largest .html in this folder (~44 MB),
rem so a stray readme.html saved next to it cannot be picked by mistake.
for %%f in ("%~dp0*.html") do if %%~zf GTR 10000000 set "PAGE=%%~nxf"
if not defined PAGE (
  echo [ERROR] No tool html found in this folder.
  pause
  exit /b 1
)

set "BROWSER="
for %%p in (
  "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  "%LocalAppData%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
) do if not defined BROWSER if exist %%p set "BROWSER=%%~p"

if defined BROWSER (
  echo Opening with high-performance GPU: %BROWSER%
  start "" "%BROWSER%" --force_high_performance_gpu "%~dp0%PAGE%"
) else (
  echo Chrome/Edge not found - opening with the default browser.
  echo NOTE: WebGPU may then run on the integrated GPU.
  start "" "%~dp0%PAGE%"
)
exit /b 0
