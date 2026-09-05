$f = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\s2c-startup.bat"
@'
@echo off
start "s2c" /min powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\AI-LAB\screenshot-to-code\scripts\start-s2c.ps1"
'@ | Out-File -FilePath $f -Encoding ascii
Write-Output "Created: $f"
