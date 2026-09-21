@echo off
cd /d "%~dp0"
title 月读 (LunePaper) 启动器

echo ========================================================
echo             月读 (LunePaper) 一键启动脚本
echo ========================================================
echo.

REM 1. 查找可用 Python 解释器 (优先 LunePaper 专用 conda 环境)
set "PYTHON_EXE="
if exist "D:\miniconda\envs\py3.10\python.exe" (
    set "PYTHON_EXE=D:\miniconda\envs\py3.10\python.exe"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo [错误] 未检测到可用的 Python 环境，请确认已安装 Python 并配置环境变量！
    pause
    exit /b 1
)

echo [*] 使用 Python 解释器: %PYTHON_EXE%

REM 2. 检查本地历史任务记录
if exist "history" (
    for /f %%c in ('dir /b /ad history ^| find /c /v ""') do (
        echo [*] 检测到本地已存储的翻译历史: %%c 篇
    )
)

REM 3. 启动后端服务 [端口 7860]
netstat -ano | findstr ":7860" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [*] 后端服务已在端口 7860 运行中，无需重复启动。
) else (
    echo [*] [1/2] 正在启动后端服务 http://localhost:7860 ...
    start "月读 - 后端服务" cmd /k "title 月读 - 后端服务 [Port 7860] & cd /d "%~dp0" & "%PYTHON_EXE%" backend/main.py"
)

REM 4. 启动前端服务 [端口 5173]
netstat -ano | findstr ":5173" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [*] 前端服务已在端口 5173 运行中，无需重复启动。
) else (
    echo [*] [2/2] 正在启动前端服务 http://localhost:5173 ...
    start "月读 - 前端界面" cmd /k "title 月读 - 前端界面 [Port 5173] & cd /d "%~dp0frontend" & npm run dev"
)

echo.
echo ========================================================
echo  月读已在后台启动！
echo  - 前端界面: http://localhost:5173
echo  - 后端接口: http://localhost:7860
echo ========================================================
echo.
echo [*] 正在打开浏览器访问月读系统...
ping 127.0.0.1 -n 4 >nul
start http://localhost:5173

exit /b 0
