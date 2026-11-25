@echo off
cd /d "%~dp0"
if not exist "pyproject.toml" (
  echo This file must be run from the unzipped project folder, not from inside the zip.
  echo Open D:\Project\flowline-materials-planner in File Explorer and double-click it there.
  echo If that folder does not exist, right-click the zip, choose Extract All, then try again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\activate.bat" (
  echo Run install_windows.bat first.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
echo Opening FlowLine Materials Planner in your browser. Close this window to stop it.
streamlit run app\streamlit_app.py
pause
