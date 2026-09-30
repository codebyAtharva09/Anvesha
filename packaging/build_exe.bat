@echo off
cd /d "%~dp0\.."
python -m pip install pyinstaller
pyinstaller packaging\anvesha.spec --noconfirm
echo Built: dist\ANVESHA\ANVESHA.exe
pause
