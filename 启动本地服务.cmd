@echo off
rem ============================================================
rem  Local-server launcher for the offline OCR tool.
rem  Starts a tiny static server on 127.0.0.1 and opens the page
rem  with --force_high_performance_gpu so WebGPU uses the
rem  discrete GPU on dual-GPU laptops.
rem
rem  The server runs in THIS window: closing the window (or
rem  pressing Ctrl+C) stops it. The already-open page keeps
rem  working after that, because the html is fully self-contained.
rem
rem  Usage: put this file, the .ps1 server and the html in one folder,
rem  then double-click. No Python required - Windows PowerShell is
rem  part of every supported Windows.
rem  (This file is kept pure ASCII on purpose: cmd.exe decodes batch
rem   files with the console code page, so literal non-ASCII here would
rem   break on non-Chinese Windows.)
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

rem The server itself lives in the .ps1 beside this file. It is found by
rem wildcard instead of a literal name so this launcher stays pure ASCII.
set "PS1="
for %%s in ("%~dp0*.ps1") do if not defined PS1 set "PS1=%%~fs"
if not defined PS1 (
  echo [ERROR] The .ps1 server script is missing from this folder.
  echo Keep this launcher and the .ps1 server together with the html.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Port %PORT% -Page "%PAGE%"
pause
exit /b 0
