@echo off
rem IPGuard gate CLI wrapper (Windows)
rem Usage: ipguard-gate --max 20 && start "" "https://claude.ai" || echo blocked
cd /d "%~dp0\.."
python -m ipguard.gate_cli %*
exit /b %errorlevel%
