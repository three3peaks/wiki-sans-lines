@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Python не найден. Установите Python 3 и отметьте "Add python.exe to PATH".
  pause
  exit /b 1
)

%PY% build_exe.py
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo Сборка не удалась.
  pause
  exit /b %ERR%
)
echo.
pause
