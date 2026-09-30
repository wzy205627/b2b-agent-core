 @echo off
chcp 65001 >nul
echo ================================================================
echo   正在启动 3C 电子智能销售风控审批平台 (B2B Agent Deal Desk)
echo ================================================================
echo.

:: 1. 检查并确保 Docker 容器启动
echo [1/3] 检查并唤醒 PostgreSQL (pgvector) 数据库...
docker start b2b-agent-postgres >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [提示] 正在尝试通过 docker compose 启动容器...
    docker compose up -d >nul 2>&1
)

:: 2. 启动后端 FastAPI 服务 (端口 8000)
echo [2/3] 启动后端 FastAPI 服务 (http://127.0.0.1:8000)...
start "B2B-Agent-Backend" cmd /k "cd /d %~dp0 && title B2B Agent Backend :8000 && .venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload"

:: 3. 启动前端 Vite 界面 (端口 5173)
echo [3/3] 启动前端 React 工作台 (http://localhost:5173)...
start "B2B-Agent-Frontend" cmd /k "cd /d %~dp0agent-inbox && title B2B Agent Frontend :5173 && npm run dev"

echo.
echo ================================================================
echo   启动完成！两个服务窗口已在后台打开：
echo   - 销售与主管工作台: http://localhost:5173/
echo   - 后端 Swagger 文档: http://127.0.0.1:8000/docs
echo ================================================================
echo 正在自动为您打开浏览器...
timeout /t 3 >nul
start http://localhost:5173/
