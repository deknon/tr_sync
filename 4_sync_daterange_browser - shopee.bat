@echo off
chcp 65001 >nul
echo ============================================
echo  TRCloud Browser Sync - DATE RANGE
echo  รันทุก shop หลายวัน (start - end date)
echo ============================================
echo.

SET /P START_DATE=วันเริ่มต้น (YYYY-MM-DD): 
IF "%START_DATE%"=="" (
    echo  ❌ กรุณาระบุวันเริ่มต้น
    pause
    exit /b
)

SET /P END_DATE=วันสิ้นสุด   (YYYY-MM-DD): 
IF "%END_DATE%"=="" (
    echo  ❌ กรุณาระบุวันสิ้นสุด
    pause
    exit /b
)

echo.
echo  >> Sync วันที่ %START_DATE% ถึง %END_DATE%
echo.

python "%~dp0trcloud_sync_browser.py" --platform shopee --start-date %START_DATE% --end-date %END_DATE%

echo.
echo ------------------------------------------
echo  Log saved in: logs\sync_*.txt
echo  Opening logs folder...
explorer "%~dp0logs"
echo.
pause
