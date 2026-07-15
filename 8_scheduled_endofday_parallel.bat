@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

:: ── วิธีใช้งาน (สั้นๆ) ────────────────────────
:: เหมือน 7_scheduled_endofday.bat ทุกอย่าง (ORDER D-0 → STATUS D-3..D-1 → FULL INVOICE
:: D-3..D-0) แต่แต่ละขั้นตอนรัน Shopee/Tiktok/Lazada แยกหน้าต่างพร้อมกัน (เร็วกว่า) แล้วรอ
:: ให้ทั้ง 3 หน้าต่างของขั้นตอนนั้นเสร็จก่อน ค่อยไปขั้นตอนถัดไป — FULL INVOICE ต้องรอ ORDER
:: เสร็จก่อนเสมอ เพราะต้องใช้ข้อมูล items/full-tax ที่ ORDER เพิ่ง sync เข้า TRCloud
:: (ทำขนานข้ามขั้นตอนไม่ได้ ข้อมูลจะไม่ครบ) — ทำขนานได้แค่ "ข้าม platform" ภายในขั้นตอนเดียวกัน
::
:: ไฟล์นี้ซับซ้อนกว่า 7_scheduled_endofday.bat (ใช้ temp .bat + marker file รอ 3 หน้าต่างจบ)
:: ถ้ามีปัญหา/debug ยาก ให้สลับ Task Scheduler กลับไปใช้ 7_scheduled_endofday.bat แทนได้เลย
::
:: ⚠ ต้องตั้ง Task Scheduler เป็น "Run only when user is logged on" (ห้ามใช้ "Run whether
:: user is logged on or not") เพราะ start ที่เปิดหน้าต่างแยกต่อ platform ต้องการ desktop
:: session จริง ถ้ารันแบบไม่มี session (background service) หน้าต่างจะเปิดไม่ได้เลย
::
:: จบทุกขั้นตอนแล้วส่งอีเมลสรุปผลรวมครั้งเดียว
:: log ของแต่ละขั้นตอน/ร้านถูกบันทึกอัตโนมัติอยู่แล้วที่ logs\text\run_ORDER_*.txt,
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
echo  TRCloud End-of-Day Sync (Parallel by platform)  [%date% %time%]
echo  Date range: %START_DATE% to %END_DATE%
echo ============================================================
echo.

:: Clear any leftover marker files from a previous (e.g. crashed) run
del /q "%TEMP%\trc_marker_*.flag" >nul 2>&1

:: ── ORDER — today (D-0) only, per-platform parallel ──
echo [ORDER] Start: %time%
set "P_LABEL=ORDER"
set "P_CMD=python "%~dp0trcloud_sync_browser.py" --start-date %END_DATE% --end-date %END_DATE% --no-notify"
call :RUN_STEP_PARALLEL
set ORDER_EXIT=%STEP_EXIT%
echo [ORDER] End  : %time%
echo.

:: ── STATUS — D-3 to D-1, per-platform parallel ──
echo [STATUS] Start: %time%
set "P_LABEL=STATUS"
set "P_CMD=python "%~dp0trcloud_sync_browser.py" --status --lookback 3 --no-notify"
call :RUN_STEP_PARALLEL
set STATUS_EXIT=%STEP_EXIT%
echo [STATUS] End  : %time%
echo.

:: ── FULL INVOICE safety net — D-3 to D-0, per-platform parallel ──
echo [FULL INVOICE] Start: %time%
set "P_LABEL=FULLINVOICE"
set "P_CMD=python "%~dp0trcloud_sync_browser.py" --full-invoice --start-date %START_DATE% --end-date %END_DATE% --no-notify"
call :RUN_STEP_PARALLEL
set INVOICE_EXIT=%STEP_EXIT%
echo [FULL INVOICE] End  : %time%
echo.

goto AFTER_STEPS

:: ── Run one step (P_LABEL/P_CMD) across Shopee/Tiktok/Lazada in parallel windows,
::    wait for all 3 to finish, then set STEP_EXIT (0=all ok, 1=at least one failed) ──
:RUN_STEP_PARALLEL
setlocal EnableDelayedExpansion
for %%G in (shopee tiktok lazada) do (
    set "TMPBAT=%TEMP%\trc_step_%P_LABEL%_%%G.bat"
    set "MARKER=%TEMP%\trc_marker_%P_LABEL%_%%G.flag"
    del /q "!MARKER!" >nul 2>&1
    > "!TMPBAT!" (
        echo @echo off
        echo chcp 65001 ^>nul
        echo %P_CMD% --platform %%G
        echo ^> "!MARKER!" echo %%ERRORLEVEL%%
    )
    start "TRCloud %P_LABEL% - %%G" cmd /c "!TMPBAT!"
)

:: รอสูงสุด 4 ชม. (2880 x 5 วิ) กัน hang ค้างตลอดไปถ้า start ล้มเหลว/marker ไม่มาสักที
set /a WAIT_COUNT=0
set /a WAIT_MAX=2880

:WAIT_LOOP
set /a READY=0
for %%G in (shopee tiktok lazada) do (
    if exist "%TEMP%\trc_marker_%P_LABEL%_%%G.flag" set /a READY+=1
)
if !READY! LSS 3 (
    set /a WAIT_COUNT+=1
    if !WAIT_COUNT! GEQ !WAIT_MAX! (
        echo   ⚠ %P_LABEL%: timeout after 4h waiting for all platforms — continuing anyway
        goto WAIT_TIMEOUT
    )
    ping -n 6 127.0.0.1 >nul
    goto WAIT_LOOP
)

set "RESULT=0"
for %%G in (shopee tiktok lazada) do (
    set /p CODE=<"%TEMP%\trc_marker_%P_LABEL%_%%G.flag"
    if not "!CODE!"=="0" set "RESULT=1"
)
endlocal & set STEP_EXIT=%RESULT%
goto :eof

:WAIT_TIMEOUT
endlocal & set STEP_EXIT=1
goto :eof

:AFTER_STEPS
:: Combined email notification
set ORDER_STATUS=success
if not "%ORDER_EXIT%"=="0" set ORDER_STATUS=failed

set STATUS_RESULT=success
if not "%STATUS_EXIT%"=="0" set STATUS_RESULT=failed

set INVOICE_STATUS=success
if not "%INVOICE_EXIT%"=="0" set INVOICE_STATUS=failed

python -c "from trcloud_sync_browser import notify_gmail; notify_gmail('[TRCloud] End-of-day sync %END_DATE% done (parallel)', 'End-of-day sync (after shipping, parallel by platform) completed\n\nORDER (D-0, Step 1-3)     : %ORDER_STATUS%\nSTATUS (D-3 to D-1)       : %STATUS_RESULT%\nFULL INVOICE (D-3 to D-0) : %INVOICE_STATUS%\n\nLog: logs\\text\\run_ORDER_*.txt, run_STATUS_*.txt, run_FULL_INVOICE_*.txt')"

echo ============================================================
echo  Done  [%date% %time%]
echo ============================================================
echo.

endlocal
