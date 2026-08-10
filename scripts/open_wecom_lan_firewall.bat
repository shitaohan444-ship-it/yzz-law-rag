@echo off
REM Add inbound firewall rule for LAN port 18192 (run as Administrator).
REM Right-click this file -> "Run as administrator".
netsh advfirewall firewall add rule name="WeCom Archive LAN (18192)" dir=in action=allow protocol=TCP localport=18192 profile=private
echo.
if %errorlevel%==0 (
  echo OK. LAN devices can now open http://192.168.0.88:18192/admin
) else (
  echo FAILED. Please right-click and "Run as administrator".
)
echo.
pause
