@echo off
chcp 65001 >nul
cd /d %~dp0
python -m pip install -r requirements.txt
pyinstaller --onefile --noconsole --name vm-trans main.py
echo.
echo 打包完成: dist\vm-trans.exe
pause
