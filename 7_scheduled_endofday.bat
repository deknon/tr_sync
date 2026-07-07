@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

:: ── วิธีใช้งาน (สั้นๆ) ────────────────────────
:: ใช้กับ Windows Task Scheduler รันตอนสิ้นวัน (หลังส่งของ) ไม่มี prompt โต้ตอบ
:: sync ORDER (Step 1-3) ทุก platform หน้าต่างเดียว ช่วง D-3 ถึงวันนี้ (D-0) เพื่อให้
:: สต๊อกตัดตรงตามคำสั่งซื้อที่ส่งออกจริง แล้วต่อด้วย FULL INVOICE (Outstanding only)
:: ช่วงวันเดียวกัน กันบิลตกหล่น จบแล้วส่งอีเมลสรุปผลรวมครั้งเดียว
:: log ของแต่ละขั้นตอนถูกบันทึกอัตโนมัติอยู่แล้วที่ logs\text\run_ORDER_*.txt
:: และ logs\text\run_FULLINVOICE_*.txt (ไม่ต้องตั้งค่าเพิ่ม)
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

:: ORDER sync (Step 1-3, includes per-shop/day FULL INVOICE, all shops, single window)
echo [ORDER] Start: %time%
python "%~dp0trcloud_sync_browser.py" --start-date %START_DATE% --end-date %END_DATE% --no-notify
set ORDER_EXIT=%ERRORLEVEL%
echo [ORDER] End  : %time%
echo.

:: FULL INVOICE safety net (Outstanding only, same date range as ORDER)
echo [FULL INVOICE] Start: %time%
python "%~dp0trcloud_sync_browser.py" --full-invoice --start-date %START_DATE% --end-date %END_DATE% --no-notify
set INVOICE_EXIT=%ERRORLEVEL%
echo [FULL INVOICE] End  : %time%
echo.

:: Combined email notification
set ORDER_STATUS=success
if not %ORDER_EXIT%==0 set ORDER_STATUS=failed

set INVOICE_STATUS=success
if not %INVOICE_EXIT%==0 set INVOICE_STATUS=failed

python -c "from trcloud_sync_browser import notify_gmail; notify_gmail('[TRCloud] End-of-day sync %START_DATE% to %END_DATE% done', 'End-of-day sync (after shipping) completed for %START_DATE% to %END_DATE%\n\nORDER (Step 1-3) : %ORDER_STATUS%\nFULL INVOICE     : %INVOICE_STATUS%\n\nLog: logs\\text\\run_ORDER_*.txt, run_FULLINVOICE_*.txt')"

echo ============================================================
echo  Done  [%date% %time%]
echo ============================================================
echo.

endlocal
