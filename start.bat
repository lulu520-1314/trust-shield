@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   信任守护师 · 美妆内容真实性核验
echo   浏览器将自动打开 http://127.0.0.1:8899
echo   关闭本窗口即停止服务
echo ============================================
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8899"
python -m uvicorn app.server:app --host 127.0.0.1 --port 8899
pause
