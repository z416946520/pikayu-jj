@echo off
rem pikafishjj GUI launcher - starts the tkinter console with the bundled Python.
setlocal
set PY=D:\dshdesktop\DSH Desktop\resources\office-runtime\primary-runtime\dependencies\python\python.exe
set PKG=%~dp0pikafishjj
if not exist "%PY%" set PY=python
cd /d "%PKG%"
start "pikafishjj" /d "%PKG%" "%PY%" -m pikafishjj.run ui
endlocal
