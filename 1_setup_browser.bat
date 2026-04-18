@echo off
chcp 65001 >/dev/null
echo ============================================
echo  TRCloud Browser Sync - SETUP
echo  Install Playwright + Login session
echo ============================================
echo.

echo Installing Playwright...
pip install playwright --break-system-packages
python -m playwright install chromium

echo.
echo Starting browser for login...
python "%~dp0trcloud_sync_browser.py" --setup

echo.
echo Setup complete. Press any key to close.
pause
