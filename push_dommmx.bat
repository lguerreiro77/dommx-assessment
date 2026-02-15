@echo off
echo ==========================================
echo   DOMMx - Push to GitHub
echo ==========================================
echo.

git init
git add .
git commit -m "Update DOMMx Technical Diagnostic"
git branch -M main
git remote remove origin 2>nul
git remote add origin https://github.com/lguerreiro77/dommx-assessment.git
git push -u origin main

echo.
echo ==========================================
echo   Push completed
echo ==========================================
pause
