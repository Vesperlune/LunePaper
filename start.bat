@echo off
chcp 65001 >nul
title LunePaper 启动器

echo ========================================================
echo             月读 (LunePaper) 一键启动脚本
echo ========================================================

set PYTHON_EXE=python
where python >nul 2>nul
if %errorlevel% neq 0 (
    if exist "D:\miniconda\envs\py3.10\python.exe" (
        set PYTHON_EXE=D:\miniconda\envs\py3.10\python.exe
    )
) else (
    REM Check if default python has fastapi
    python -c "import fastapi" >nul 2>nul
    if %errorlevel% neq 0 (
        if exist "D:\miniconda\envs\py3.10\python.exe" (
            set PYTHON_EXE=D:\miniconda\envs\py3.10\python.exe
        )
    )
)

echo [*] 使用 Python 解释器: %PYTHON_EXE%
echo [*] [1/2] 正在启动后端服务 (http://localhost:7860)...
start "LunePaper Backend" cmd /k "%PYTHON_EXE% backend/main.py"

echo [*] [2/2] 正在启动前端服务 (http://localhost:5173)...
start "LunePaper Frontend" cmd /k "cd frontend && npm run dev"

echo ========================================================
echo  月读已在后台启动！
echo  - 前端界面: http://localhost:5173
echo  - 后端接口: http://localhost:7860
echo ========================================================
