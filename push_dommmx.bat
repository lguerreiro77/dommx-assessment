@echo off
echo ==========================================
echo   DOMMx - Update Existing Repo
echo ==========================================
echo.

echo Pulling latest changes from GitHub...
git pull origin main

echo.
echo Adding local changes...
git add .

echo.
echo Creating commit...
git commit -m "Update DOMMx"

echo.
echo Pushing to GitHub...
git push origin main

echo.
echo ==========================================
echo   Update completed
echo ==========================================
pause
