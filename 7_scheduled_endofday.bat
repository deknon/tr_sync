@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

:: ── วิธีใช้งาน (สั้นๆ) ────────────────────────
:: ใช้กับ Windows Task Scheduler รันตอนสิ้นวัน (หลังส่งของ) ไม่มี prompt โต้ตอบ
:: - วันนี้ (D-0): ORDER เต็ม (Step 1-3) เพราะเป็น order ใหม่ ต้อง sync items/tax ครั้งแรก
:: - D-3 ถึง D-1: STATUS อย่างเดียว (Step 1 + Step 2 เฉพาะ Shopee) แค่พอเช็ค/อัปเดต
::   สถานะที่เปลี่ยนตอนส่งของสิ้นวัน ไม่ต้อง sync items/full-tax ซ้ำ (เคย sync แล้วตอนเป็น D-0)
:: - FULL INVOICE (Outstanding only) คลุม D-3 ถึง D-0 ทั้งช่วง เป็น safety net กันบิลตกหล่น
:: ทุก platform หน้าต่างเดียว (เรียบง่าย รันทีละขั้นตอน) จบแล้วส่งอีเมลสรุปผลรวมครั้งเดียว
:: ถ้าต้องการเวอร์ชันเร็วกว่านี้ (แยกหน้าต่างต่อ platform) ดูไฟล์ 8_scheduled_endofday_parallel.bat
:: log ของแต่ละขั้นตอนถูกบันทึกอัตโนมัติอยู่แล้วที่ logs\text\run_ORDER_*.txt,
:: run_STATUS_*.txt และ run_FULL_INVOICE_*.txt (ไม่ต้องตั้งค่าเพิ่ม)
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

:: Calculate date range: D-3 to today (D-0)
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).AddDays(-3).ToString(\"yyyy-MM-dd\")"') do set START_DATE=%%d
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).ToString(\"yyyy-MM-dd\")"') do set END_DATE=%%d

echo.
echo ============================================================
echo  TRCloud End-of-Day Sync  [%date% %time%]
echo  Date range: %START_DATE% to %END_DATE%
echo ============================================================
echo.

:: ORDER sync — today (D-0) only, full Step 1-3 + built-in per-shop/day FULL INVOICE
echo [ORDER] Start: %time%
python "%~dp0trcloud_sync_browser.py" --start-date %END_DATE% --end-date %END_DATE% --no-notify
set ORDER_EXIT=%ERRORLEVEL%
echo [ORDER] End  : %time%
echo.

:: STATUS sync — D-3 to D-1 (already went through Step 1-3 on their own D-0 night;
:: just refresh status here, e.g. orders that changed when shipped today)
echo [STATUS] Start: %time%
python "%~dp0trcloud_sync_browser.py" --status --lookback 3 --no-notify
set STATUS_EXIT=%ERRORLEVEL%
echo [STATUS] End  : %time%
echo.

:: FULL INVOICE safety net (Outstanding only, D-3 to D-0 — same range as before)
echo [FULL INVOICE] Start: %time%
python "%~dp0trcloud_sync_browser.py" --full-invoice --start-date %START_DATE% --end-date %END_DATE% --no-notify
set INVOICE_EXIT=%ERRORLEVEL%
echo [FULL INVOICE] End  : %time%
echo.

:: Combined email notification
set ORDER_STATUS=success
if not %ORDER_EXIT%==0 set ORDER_STATUS=failed

set STATUS_RESULT=success
if not %STATUS_EXIT%==0 set STATUS_RESULT=failed

set INVOICE_STATUS=success
if not %INVOICE_EXIT%==0 set INVOICE_STATUS=failed

python -c "from trcloud_sync_browser import notify_gmail; notify_gmail('[TRCloud] End-of-day sync %END_DATE% done', 'End-of-day sync (after shipping) completed\n\nORDER (D-0, Step 1-3)     : %ORDER_STATUS%\nSTATUS (D-3 to D-1)       : %STATUS_RESULT%\nFULL INVOICE (D-3 to D-0) : %INVOICE_STATUS%\n\nLog: logs\\text\\run_ORDER_*.txt, run_STATUS_*.txt, run_FULL_INVOICE_*.txt')"

echo ============================================================
echo  Done  [%date% %time%]
echo ============================================================
echo.

endlocal
