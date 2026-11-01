@echo off
chcp 936 >nul
title AI 语音输入法 · 客户端
cd /d "%~dp0"

echo.
echo  ==========================================
echo     AI 语音输入法 · 客户端
echo     按一下右 Alt 开始录音，再按一下结束
echo     关闭主窗口会最小化到托盘
echo  ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo  [错误] 没有找到 Python。
    echo  请先安装 Python 3.10 或更高版本，并勾选 Add Python to PATH。
    echo.
    pause
    exit /b 1
)

echo  [启动中] 正在运行 python client_main.py ...
echo.
python client_main.py

if errorlevel 1 (
    echo.
    echo  [提示] 程序异常退出。
    echo  如果提示缺少依赖，请先执行： pip install -r requirements.txt
    echo.
)
pause
