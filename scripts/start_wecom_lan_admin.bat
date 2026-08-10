@echo off
REM ============================================================
REM WeCom chat archive - LAN access launcher
REM
REM Two components:
REM   1) SSH tunnel:  127.0.0.1:18191 -> Aliyun wecom-archive (127.0.0.1:18190)
REM   2) LAN proxy:   0.0.0.0:18192   -> 127.0.0.1:18191
REM      so LAN devices open http://192.168.0.88:18192/admin
REM
REM Close this window to stop both.
REM ============================================================
setlocal
set TUNNEL_PORT=18191
set LAN_PORT=18192
set VENV_PY=D:\law-rag-project\law-rag-service\.venv\Scripts\python.exe
set PROXY=D:\law-rag-project\scripts\wecom_lan_proxy.py

echo [1/2] Starting SSH tunnel wecom-archive (127.0.0.1:%TUNNEL_PORT% -^> Aliyun 127.0.0.1:18190) ...
start "wecom-archive-tunnel" ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -N -L %TUNNEL_PORT%:127.0.0.1:18190 wecom-archive
timeout /t 4 /nobreak >nul

echo [2/2] Starting LAN proxy (0.0.0.0:%LAN_PORT% -^> 127.0.0.1:%TUNNEL_PORT%) ...
echo.
echo     LAN access:    http://192.168.0.88:%LAN_PORT%/admin
echo     Local access:  http://127.0.0.1:%LAN_PORT%/admin
echo.
"%VENV_PY%" "%PROXY%"
endlocal
