@echo off
echo ==========================
echo Setting up DOMMx project
echo ==========================

IF NOT EXIST .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating virtual environment...
call .venv\Scripts\activate

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing requirements...
pip install -r requirements.txt

echo Activating virtual environment...
call .venv\Scripts\activate

pause

echo ==========================
echo Setup complete.
echo ==========================
pause

@echo off

IF EXIST .venv (
    cmd /k ".venv\Scripts\activate"
)

