@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

:: ── วิธีใช้งาน (สั้นๆ) ────────────────────────
:: ใช้กับ Windows Task Scheduler รันอัตโนมัติทุกวัน (ไม่มี prompt โต้ตอบ)
:: sync ย้อนหลัง 1 วัน (D-1) ทุก platform: ORDER (รวม FULL INVOICE) แล้วต่อด้วย RV
:: จบแล้วส่งอีเมลสรุปผลรวมครั้งเดียว — ไม่ต้อง config อะไรเพิ่ม แค่ตั้ง schedule ให้รันไฟล์นี้
:: ────────────────────────────────────────────

cd /d "%~dp0"

:: Ensure Git is reachable (Task Scheduler uses minimal PATH)
set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;C:\Program Files (x86)\Git\cmd"

:: Auto-update from GitHub
where git >nul 2>&1
if errorlevel 1 (
    echo [git] Skipped: git not found in PATH
) else (
    git -C "%~dp0" pull --ff-only --quiet 2>nul
    if errorlevel 1 (
        echo [git] Pull skipped ^(local changes or no network^)
    ) else (
        echo [git] Updated from GitHub
    )
)

:: Calculate yesterday (D-1)
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).AddDays(-1).ToString(\"yyyy-MM-dd\")"') do set YESTERDAY=%%d

echo.
echo ============================================================
echo  TRCloud Auto Sync  [%date% %time%]
echo  Target date: %YESTERDAY%
echo ============================================================
echo.

:: ORDER sync (includes FULL INVOICE download to TRCloud per shop/day)
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

:: Email notification — ส่งเฉพาะตอนมี error/fail เท่านั้น (สำเร็จหมดไม่ต้องส่งรบกวน)
set ORDER_STATUS=success
if not "%ORDER_EXIT%"=="0" set ORDER_STATUS=failed

set RV_STATUS=success
if not "%RV_EXIT%"=="0" set RV_STATUS=failed

if "%ORDER_STATUS%%RV_STATUS%"=="successsuccess" (
    echo [email] All steps succeeded — no notification email sent.
) else (
    python -c "from trcloud_sync_browser import notify_gmail; notify_gmail('[TRCloud] Scheduled sync %YESTERDAY% FAILED', 'Scheduled sync for %YESTERDAY% had failure(s)\n\nORDER : %ORDER_STATUS%\nRV    : %RV_STATUS%')"
)

echo ============================================================
echo  Done  [%date% %time%]
echo ============================================================
echo.

endlocal
