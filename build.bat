@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .build-venv\Scripts\python.exe (
    echo 首次构建:创建独立构建环境...
    python -m venv .build-venv
    .build-venv\Scripts\python -m pip install -r requirements.txt
)
echo 开始打包(onedir,启动快)...
.build-venv\Scripts\pyinstaller --onedir --noconsole --name vm-trans main.py
echo.
echo 打包完成: dist\vm-trans\vm-trans.exe
echo 分发: 将 dist\vm-trans 文件夹压缩为 zip 后发送
pause
