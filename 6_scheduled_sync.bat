@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: Auto-update from GitHub
git -C "%~dp0" pull --ff-only --quiet 2>nul && (
    echo [git] Updated from GitHub
) || (
    echo [git] Pull skipped
)

:: Calculate yesterday (D-1)
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).AddDays(-1).ToString(\"yyyy-MM-dd\")"') do set YESTERDAY=%%d

echo.
echo ============================================================
echo  TRCloud Auto Sync  [%date% %time%]
echo  Target date: %YESTERDAY%
echo ============================================================
echo.

:: ORDER sync
echo [ORDER] Start: %time%
python "%~dp0trcloud_sync_browser.py" --start-date %YESTERDAY% --end-date %YESTERDAY% --no-notify
set ORDER_EXIT=%ERRORLEVEL%
echo [ORDER] End  : %time%
echo.

:: RV sync
echo [RV] Start: %time%
python "%~dp0trcloud_sync_browser.py" --rv --start-date %YESTERDAY% --end-date %YESTERDAY% --no-notify
set RV_EXIT=%ERRORLEVEL%
echo [RV] End  : %time%
echo.

:: STATUS sync (Step 1 only, D-14 auto)
echo [STATUS] Start: %time%
python "%~dp0trcloud_sync_browser.py" --status --no-notify
set STATUS_EXIT=%ERRORLEVEL%
echo [STATUS] End  : %time%
echo.

:: RETURN ITEM sync (Step 6, Shopee only)
echo [RETURN] Start: %time%
python "%~dp0trcloud_sync_browser.py" --return-item --start-date %YESTERDAY% --end-date %YESTERDAY% --no-notify
set RETURN_EXIT=%ERRORLEVEL%
echo [RETURN] End  : %time%
echo.

:: Combined email notification
set ORDER_STATUS=success
if not %ORDER_EXIT%==0 set ORDER_STATUS=failed

set RV_STATUS=success
if not %RV_EXIT%==0 set RV_STATUS=failed

set STATUS_STATUS=success
if not %STATUS_EXIT%==0 set STATUS_STATUS=failed

set RETURN_STATUS=success
if not %RETURN_EXIT%==0 set RETURN_STATUS=failed

python -c "from trcloud_sync_browser import notify_gmail; notify_gmail('[TRCloud] Scheduled sync %YESTERDAY% done', 'Scheduled sync completed for %YESTERDAY%\n\nORDER  : %ORDER_STATUS%\nRV     : %RV_STATUS%\nSTATUS : %STATUS_STATUS%\nRETURN : %RETURN_STATUS%')"

echo ============================================================
echo  Done  [%date% %time%]
echo ============================================================
echo.

endlocal
