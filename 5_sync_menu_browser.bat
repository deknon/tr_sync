@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

:: ── วิธีใช้งานเมนู (สั้นๆ) ────────────────────
:: ORDER        : ดึงออเดอร์เข้า TRCloud (Step 1+2+3) แล้วโหลด FULL INVOICE (IV) ต่อทันที
::                ต้องระบุ platform + ช่วงวันที่
:: RV           : sync ใบเสร็จรับเงิน (RECEIPT [RV]) ต้องระบุ platform + ช่วงวันที่
:: ALL          : รัน ORDER แล้วต่อด้วย RV ในการรันครั้งเดียว
:: STATUS       : อัพเดทสถานะออเดอร์เท่านั้น (Step 1, Shopee เพิ่ม Step 2 Sync Items) ย้อนหลัง 14 วันอัตโนมัติ ไม่ต้องใส่วันที่
:: RETURN ITEM  : sync ออเดอร์ตีคืน (Step 6) เฉพาะ Shopee ต้องระบุช่วงวันที่
:: FULL INVOICE : โหลด SO เข้า TRCloud ตรงๆ โดยไม่ sync Step 1/2/3 ก่อน (ข้อมูล sync ครบแล้ว
::                แต่บิลยังไม่เข้า/ต้องโหลดซ้ำ) ต้องระบุ platform + ช่วงวันที่
:: PARALLEL     : เลือก platform = [P]/[9] ใน ORDER/RV/ALL/STATUS/FULL INVOICE เพื่อรัน
::                Shopee/Tiktok/Lazada พร้อมกันคนละหน้าต่าง
:: ────────────────────────────────────────────

:: ── Auto-update from GitHub ──────────────────
git -C "%~dp0" pull --ff-only --quiet 2>nul && (
    echo [git] Updated from GitHub
) || (
    echo [git] Pull skipped ^(no git / no remote / local changes^)
)
echo.

echo ============================================
echo  TRCloud Browser Sync - MENU
echo ============================================
echo.
echo Select function (1 char or number):
echo   [O] or [1] = Sync ORDER         (Step 1+2+3 + FULL INVOICE)
echo   [R] or [2] = Sync RV            (Receipt)
echo   [A] or [3] = Sync ALL           (ORDER + RV)
echo   [S] or [4] = Sync STATUS        (Step 1, D-14 auto; Shopee +Step 2 Items)
echo   [N] or [5] = Sync RETURN ITEM   (Step 6, Shopee only)
echo   [I] or [6] = Sync FULL INVOICE  (download SO to TRCloud only, no sync first)
echo.
echo   NOTE: ORDER now auto-loads FULL INVOICE (IV) to TRCloud after
echo         order sync of each shop/day — takes longer on busy days.
echo.
set /p FUNC_CHOICE=Function:
if "%FUNC_CHOICE%"=="" (
    echo Please select function.
    pause
    exit /b 1
)

:: ── Route to function-specific flow ──
if /I "%FUNC_CHOICE%"=="S" goto ASK_STATUS
if /I "%FUNC_CHOICE%"=="4" goto ASK_STATUS
if /I "%FUNC_CHOICE%"=="N" goto ASK_RETURN
if /I "%FUNC_CHOICE%"=="5" goto ASK_RETURN

:: ── ORDER / RV / ALL — need platform + date ──
echo.
echo Select platform (1 char or number):
echo   [X] or [0] = All platforms          (1 process, sequential)
echo   [S] or [1] = Shopee
echo   [T] or [2] = Tiktok
echo   [L] or [3] = Lazada
echo   [P] or [9] = Parallel (all platforms, separate windows at once)
echo.
set /p PLATFORM_CHOICE=Platform:
if "%PLATFORM_CHOICE%"=="" (
    echo Please select platform.
    pause
    exit /b 1
)

set PLATFORM_ARG=
set PARALLEL_MODE=
if /I "%PLATFORM_CHOICE%"=="X" set PLATFORM_ARG=
if /I "%PLATFORM_CHOICE%"=="0" set PLATFORM_ARG=
if /I "%PLATFORM_CHOICE%"=="S" set PLATFORM_ARG=--platform shopee
if /I "%PLATFORM_CHOICE%"=="1" set PLATFORM_ARG=--platform shopee
if /I "%PLATFORM_CHOICE%"=="T" set PLATFORM_ARG=--platform tiktok
if /I "%PLATFORM_CHOICE%"=="2" set PLATFORM_ARG=--platform tiktok
if /I "%PLATFORM_CHOICE%"=="L" set PLATFORM_ARG=--platform lazada
if /I "%PLATFORM_CHOICE%"=="3" set PLATFORM_ARG=--platform lazada
if /I "%PLATFORM_CHOICE%"=="P" set PARALLEL_MODE=1
if /I "%PLATFORM_CHOICE%"=="9" set PARALLEL_MODE=1

if /I not "%PLATFORM_CHOICE%"=="X" if /I not "%PLATFORM_CHOICE%"=="0" if /I not "%PLATFORM_CHOICE%"=="S" if /I not "%PLATFORM_CHOICE%"=="1" if /I not "%PLATFORM_CHOICE%"=="T" if /I not "%PLATFORM_CHOICE%"=="2" if /I not "%PLATFORM_CHOICE%"=="L" if /I not "%PLATFORM_CHOICE%"=="3" if /I not "%PLATFORM_CHOICE%"=="P" if /I not "%PLATFORM_CHOICE%"=="9" (
    echo Invalid platform choice.
    pause
    exit /b 1
)

echo.
set /p START_DATE=Start date (YYYY-MM-DD):
if "%START_DATE%"=="" (
    echo Please input start date.
    pause
    exit /b 1
)
set /p END_DATE=End date   (YYYY-MM-DD):
if "%END_DATE%"=="" (
    echo Please input end date.
    pause
    exit /b 1
)

goto ASK_VISIBLE

:: ── STATUS — platform only, no date ──────────
:ASK_STATUS
echo.
echo Select platform (1 char or number):
echo   [X] or [0] = All platforms          (1 process, sequential)
echo   [S] or [1] = Shopee
echo   [T] or [2] = Tiktok
echo   [L] or [3] = Lazada
echo   [P] or [9] = Parallel (all platforms, separate windows at once)
echo.
set /p PLATFORM_CHOICE=Platform:
if "%PLATFORM_CHOICE%"=="" set PLATFORM_CHOICE=X

set PLATFORM_ARG=
set PARALLEL_MODE=
if /I "%PLATFORM_CHOICE%"=="X" set PLATFORM_ARG=
if /I "%PLATFORM_CHOICE%"=="0" set PLATFORM_ARG=
if /I "%PLATFORM_CHOICE%"=="S" set PLATFORM_ARG=--platform shopee
if /I "%PLATFORM_CHOICE%"=="1" set PLATFORM_ARG=--platform shopee
if /I "%PLATFORM_CHOICE%"=="T" set PLATFORM_ARG=--platform tiktok
if /I "%PLATFORM_CHOICE%"=="2" set PLATFORM_ARG=--platform tiktok
if /I "%PLATFORM_CHOICE%"=="L" set PLATFORM_ARG=--platform lazada
if /I "%PLATFORM_CHOICE%"=="3" set PLATFORM_ARG=--platform lazada
if /I "%PLATFORM_CHOICE%"=="P" set PARALLEL_MODE=1
if /I "%PLATFORM_CHOICE%"=="9" set PARALLEL_MODE=1

set START_DATE=auto-D14
set END_DATE=auto-D14
goto ASK_VISIBLE

:: ── RETURN ITEM — date only, platform=Shopee ──
:ASK_RETURN
echo.
echo [RETURN ITEM] Shopee only — TO_RETURN + RETURNED
echo.
set /p START_DATE=Start date (YYYY-MM-DD):
if "%START_DATE%"=="" (
    echo Please input start date.
    pause
    exit /b 1
)
set /p END_DATE=End date   (YYYY-MM-DD):
if "%END_DATE%"=="" (
    echo Please input end date.
    pause
    exit /b 1
)
set PLATFORM_ARG=
goto ASK_VISIBLE

:: ── Visible mode ──────────────────────────────
:ASK_VISIBLE
echo.
echo Visible browser mode?
echo   [V] or [1] = Visible ON
echo   [N] or [0] = Visible OFF (headless)
echo.
set /p VISIBLE_CHOICE=Visible:
if "%VISIBLE_CHOICE%"=="" set VISIBLE_CHOICE=0

set VISIBLE_ARG=
if /I "%VISIBLE_CHOICE%"=="V" set VISIBLE_ARG=--visible
if /I "%VISIBLE_CHOICE%"=="1" set VISIBLE_ARG=--visible

if /I not "%VISIBLE_CHOICE%"=="V" if /I not "%VISIBLE_CHOICE%"=="1" if /I not "%VISIBLE_CHOICE%"=="N" if /I not "%VISIBLE_CHOICE%"=="0" (
    echo Invalid visible choice.
    pause
    exit /b 1
)

:: ── Build commands ────────────────────────────
set BASE_CMD=python "%~dp0trcloud_sync_browser.py" --start-date %START_DATE% --end-date %END_DATE% %VISIBLE_ARG%
set BASE_RV_CMD=python "%~dp0trcloud_sync_browser.py" --rv --start-date %START_DATE% --end-date %END_DATE% %VISIBLE_ARG%
set BASE_STATUS_CMD=python "%~dp0trcloud_sync_browser.py" --status %VISIBLE_ARG%
set BASE_RETURN_CMD=python "%~dp0trcloud_sync_browser.py" --return-item --start-date %START_DATE% --end-date %END_DATE% %VISIBLE_ARG%
set BASE_INVOICE_CMD=python "%~dp0trcloud_sync_browser.py" --full-invoice --start-date %START_DATE% --end-date %END_DATE% %VISIBLE_ARG%

echo.
echo ============================================
echo Start sync...
if /I "%FUNC_CHOICE%"=="S" (echo Function : STATUS ^(Step 1, D-14 auto; Shopee +Step 2 Items^))
if /I "%FUNC_CHOICE%"=="4" (echo Function : STATUS ^(Step 1, D-14 auto; Shopee +Step 2 Items^))
if /I "%FUNC_CHOICE%"=="N" (echo Function : RETURN ITEM ^(Step 6, Shopee^))
if /I "%FUNC_CHOICE%"=="5" (echo Function : RETURN ITEM ^(Step 6, Shopee^))
if /I "%FUNC_CHOICE%"=="I" (echo Function : FULL INVOICE ^(download only, no sync^))
if /I "%FUNC_CHOICE%"=="6" (echo Function : FULL INVOICE ^(download only, no sync^))
if /I "%FUNC_CHOICE%"=="O" (echo Function : ORDER)
if /I "%FUNC_CHOICE%"=="1" (echo Function : ORDER)
if /I "%FUNC_CHOICE%"=="R" (echo Function : RV)
if /I "%FUNC_CHOICE%"=="2" (echo Function : RV)
if /I "%FUNC_CHOICE%"=="A" (echo Function : ALL ^(ORDER + RV^))
if /I "%FUNC_CHOICE%"=="3" (echo Function : ALL ^(ORDER + RV^))
if not "%START_DATE%"=="auto-D14" (echo Date     : %START_DATE% to %END_DATE%)
if "%START_DATE%"=="auto-D14"     (echo Date     : auto D-14 to yesterday)
if defined PARALLEL_MODE (echo Platform : PARALLEL ^(Shopee/Tiktok/Lazada, separate windows^)) else if defined PLATFORM_ARG (echo Platform : %PLATFORM_ARG%) else (echo Platform : all)
if defined VISIBLE_ARG  (echo Visible  : ON)  else (echo Visible  : OFF)
echo ============================================
echo.

if /I "%FUNC_CHOICE%"=="O" goto RUN_ORDER
if /I "%FUNC_CHOICE%"=="1" goto RUN_ORDER
if /I "%FUNC_CHOICE%"=="R" goto RUN_RV
if /I "%FUNC_CHOICE%"=="2" goto RUN_RV
if /I "%FUNC_CHOICE%"=="A" goto RUN_ALL
if /I "%FUNC_CHOICE%"=="3" goto RUN_ALL
if /I "%FUNC_CHOICE%"=="S" goto RUN_STATUS
if /I "%FUNC_CHOICE%"=="4" goto RUN_STATUS
if /I "%FUNC_CHOICE%"=="N" goto RUN_RETURN
if /I "%FUNC_CHOICE%"=="5" goto RUN_RETURN
if /I "%FUNC_CHOICE%"=="I" goto RUN_INVOICE
if /I "%FUNC_CHOICE%"=="6" goto RUN_INVOICE

echo Invalid function choice.
pause
exit /b 1

:RUN_ORDER
if defined PARALLEL_MODE (
    set "P_LABEL=ORDER"
    set "P_CMD=%BASE_CMD%"
    call :SPAWN_PARALLEL
) else (
    echo [ORDER] Running... (includes FULL INVOICE download to TRCloud)
    %BASE_CMD% %PLATFORM_ARG%
)
goto END_RUN

:RUN_RV
if defined PARALLEL_MODE (
    set "P_LABEL=RV"
    set "P_CMD=%BASE_RV_CMD%"
    call :SPAWN_PARALLEL
) else (
    echo [RV] Running...
    %BASE_RV_CMD% %PLATFORM_ARG%
)
goto END_RUN

:RUN_ALL
if defined PARALLEL_MODE (
    set "P_LABEL=ORDER"
    set "P_CMD=%BASE_CMD%"
    call :SPAWN_PARALLEL
    set "P_LABEL=RV"
    set "P_CMD=%BASE_RV_CMD%"
    call :SPAWN_PARALLEL
) else (
    echo [ALL] Step 1/2: ORDER (includes FULL INVOICE download to TRCloud)
    %BASE_CMD% %PLATFORM_ARG%
    echo.
    echo [ALL] Step 2/2: RV
    %BASE_RV_CMD% %PLATFORM_ARG%
)
goto END_RUN

:RUN_STATUS
if defined PARALLEL_MODE (
    set "P_LABEL=STATUS"
    set "P_CMD=%BASE_STATUS_CMD%"
    call :SPAWN_PARALLEL
) else (
    echo [STATUS] Running... (D-14 auto; Shopee +Step 2 Items)
    %BASE_STATUS_CMD% %PLATFORM_ARG%
)
goto END_RUN

:RUN_RETURN
echo [RETURN ITEM] Running... (Shopee only)
%BASE_RETURN_CMD%
goto END_RUN

:RUN_INVOICE
if defined PARALLEL_MODE (
    set "P_LABEL=INVOICE"
    set "P_CMD=%BASE_INVOICE_CMD%"
    call :SPAWN_PARALLEL
) else (
    echo [FULL INVOICE] Running... (download SO to TRCloud only, no sync)
    %BASE_INVOICE_CMD% %PLATFORM_ARG%
)
goto END_RUN

:: ── Spawn one platform per window (Shopee / Tiktok / Lazada) ──
:: หมายเหตุ: path ของโปรเจกต์มีเว้นวรรค (เช่น "OneDrive - Gadget Villa Co., Ltd")
:: ห้ามส่ง P_CMD (มี " ครอบ path อยู่แล้ว) ผ่าน call-argument แบบ call :X "%VAR%"
:: เพราะ quote ซ้อนกันจะทำให้ cmd tokenize argument ผิดจนตัด path ขาดตอนเว้นวรรค
:: จึงส่งผ่าน global variable (P_LABEL / P_CMD ที่ผู้เรียก set ไว้ก่อน call) แทน
:SPAWN_PARALLEL
setlocal EnableDelayedExpansion
echo [%P_LABEL%] Parallel mode: launching Shopee / Tiktok / Lazada in separate windows...
for %%G in (shopee tiktok lazada) do (
    set "TMPBAT=%TEMP%\trc_parallel_%P_LABEL%_%%G.bat"
    > "!TMPBAT!" (
        echo @echo off
        echo chcp 65001 ^>nul
        echo %P_CMD% --platform %%G
        echo echo.
        echo echo [%P_LABEL% - %%G] Done.
        echo pause
    )
    start "TRCloud %P_LABEL% - %%G" cmd /k "!TMPBAT!"
)
endlocal
goto :eof

:END_RUN
echo.
echo ------------------------------------------
if defined PARALLEL_MODE (
    echo Parallel windows launched — each platform is still running in its own window.
    echo This menu window is done; check each platform window for its result.
) else (
    echo Sync finished.
)
echo Log saved in: logs\text\run_*.txt
echo Opening logs folder...
explorer "%~dp0logs"
echo.
pause
