@echo off
setlocal
cd /d "%~dp0"
if not exist "pyproject.toml" (
  echo This file must be run from the unzipped project folder, not from inside the zip.
  echo Open D:\Project\flowline-materials-planner in File Explorer and double-click it there.
  echo If that folder does not exist, right-click the zip, choose Extract All, then try again.
  pause
  exit /b 1
)
set "REPO=alphakfli/flowline-materials-planner"
echo Push FlowLine Materials Planner to GitHub (%REPO%)
echo.
where git >nul 2>&1
if errorlevel 1 (
  echo Git is not installed. Install it from https://git-scm.com/download/win
  echo then run this file again.
  pause
  exit /b 1
)

rem 1. Check for secrets, personal data and real company names before anything leaves this PC
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY ( where py >nul 2>&1 && set "PY=py -3" )
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if defined PY (
  %PY% scripts\check_sensitive.py
  if errorlevel 1 (
    echo.
    echo Push stopped: fix the items above first, or send this message to Claude.
    pause
    exit /b 1
  )
) else (
  echo Python not found, so the sensitive-data check was skipped. Run install_windows.bat first.
  pause
  exit /b 1
)

rem 2. First run: create the local repository and the first commit
git config --global --add safe.directory "%CD:\=/%" >nul 2>&1
if not exist ".git" (
  git init -b main
  git config user.name >nul 2>&1 || git config user.name "alphakfli"
  git config user.email >nul 2>&1 || git config user.email "alphakfli@users.noreply.github.com"
)
git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "FlowLine Materials Planner: clear-to-build, working capital, CM and supplier views"
)

rem 3. Push. Only if the repository is missing on GitHub, create it and push again
git remote get-url origin >nul 2>&1
if errorlevel 1 git remote add origin https://github.com/%REPO%.git
echo A browser window may open to sign in to GitHub. Sign in, then come back here.
git push -u origin main
if not errorlevel 1 goto done
where gh >nul 2>&1
if not errorlevel 1 (
  gh repo create %REPO% --public --description "Open-source materials planner for engineer-to-order manufacturing" >nul 2>&1
)
echo.
echo The push did not go through. If the message above says "Repository not found":
echo   open https://github.com/new, name it flowline-materials-planner, Public, no README, Create repository.
echo If the repository already exists, just press a key to try the push again.
pause
git push -u origin main
if errorlevel 1 (
  echo.
  echo The push did not finish. Copy the message above and send it to Claude.
  pause
  exit /b 1
)

:done
echo.
echo Done. Your code is on https://github.com/%REPO%
pause
