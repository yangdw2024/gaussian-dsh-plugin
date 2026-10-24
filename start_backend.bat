@echo off
REM Gaussian DSH Plugin 后端启动脚本
REM 启动 Python FastAPI 后端，默认监听 http://127.0.0.1:8765

setlocal
cd /d "%~dp0"

REM 设置 Python 路径（如已在 PATH 中可省略）
set PYTHON_EXE=D:\YDW\Trae_Gromacs\miniconda3\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

echo ========================================
echo  Gaussian DSH Plugin Backend
echo  URL: http://127.0.0.1:8765
echo  API docs: http://127.0.0.1:8765/docs
echo ========================================
echo.

set PYTHONPATH=%~dp0
"%PYTHON_EXE%" -m backend.app

endlocal
