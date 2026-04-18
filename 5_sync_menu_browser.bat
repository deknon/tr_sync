@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

:: ── Auto-update จาก GitHub ──────────────────
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
echo   [O] or [1] = Sync ORDER
echo   [R] or [2] = Sync RV
echo   [A] or [3] = Sync ALL (ORDER + RV)
echo.
set /p FUNC_CHOICE=Function: 
if "%FUNC_CHOICE%"=="" (
    echo ❌ Please select function.
    pause
    exit /b 1
)

echo.
echo Select platform (1 char or number):
echo   [X] or [0] = All platforms
echo   [S] or [1] = Shopee
echo   [T] or [2] = Tiktok
echo   [L] or [3] = Lazada
echo.
set /p PLATFORM_CHOICE=Platform: 
if "%PLATFORM_CHOICE%"=="" (
    echo ❌ Please select platform.
    pause
    exit /b 1
)

set PLATFORM_ARG=
if /I "%PLATFORM_CHOICE%"=="X" set PLATFORM_ARG=
if /I "%PLATFORM_CHOICE%"=="0" set PLATFORM_ARG=
if /I "%PLATFORM_CHOICE%"=="S" set PLATFORM_ARG=--platform shopee
if /I "%PLATFORM_CHOICE%"=="1" set PLATFORM_ARG=--platform shopee
if /I "%PLATFORM_CHOICE%"=="T" set PLATFORM_ARG=--platform tiktok
if /I "%PLATFORM_CHOICE%"=="2" set PLATFORM_ARG=--platform tiktok
if /I "%PLATFORM_CHOICE%"=="L" set PLATFORM_ARG=--platform lazada
if /I "%PLATFORM_CHOICE%"=="3" set PLATFORM_ARG=--platform lazada

if /I not "%PLATFORM_CHOICE%"=="X" if /I not "%PLATFORM_CHOICE%"=="0" if /I not "%PLATFORM_CHOICE%"=="S" if /I not "%PLATFORM_CHOICE%"=="1" if /I not "%PLATFORM_CHOICE%"=="T" if /I not "%PLATFORM_CHOICE%"=="2" if /I not "%PLATFORM_CHOICE%"=="L" if /I not "%PLATFORM_CHOICE%"=="3" (
    echo ❌ Invalid platform choice.
    pause
    exit /b 1
)

echo.
set /p START_DATE=Start date (YYYY-MM-DD): 
if "%START_DATE%"=="" (
    echo ❌ Please input start date.
    pause
    exit /b 1
)

set /p END_DATE=End date   (YYYY-MM-DD): 
if "%END_DATE%"=="" (
    echo ❌ Please input end date.
    pause
    exit /b 1
)

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
if /I "%VISIBLE_CHOICE%"=="N" set VISIBLE_ARG=
if /I "%VISIBLE_CHOICE%"=="0" set VISIBLE_ARG=

if /I not "%VISIBLE_CHOICE%"=="V" if /I not "%VISIBLE_CHOICE%"=="1" if /I not "%VISIBLE_CHOICE%"=="N" if /I not "%VISIBLE_CHOICE%"=="0" (
    echo ❌ Invalid visible choice.
    pause
    exit /b 1
)

set BASE_CMD=python "%~dp0trcloud_sync_browser.py" --start-date %START_DATE% --end-date %END_DATE% %VISIBLE_ARG%
set BASE_RV_CMD=python "%~dp0trcloud_sync_browser.py" --rv --start-date %START_DATE% --end-date %END_DATE% %VISIBLE_ARG%

echo.
echo ============================================
echo Start sync...
echo Date range: %START_DATE% to %END_DATE%
if defined PLATFORM_ARG (
    echo Platform : %PLATFORM_ARG%
) else (
    echo Platform : all
)
if defined VISIBLE_ARG (
    echo Visible  : ON
) else (
    echo Visible  : OFF
)
echo ============================================
echo.

if /I "%FUNC_CHOICE%"=="O" goto RUN_ORDER
if /I "%FUNC_CHOICE%"=="1" goto RUN_ORDER
if /I "%FUNC_CHOICE%"=="R" goto RUN_RV
if /I "%FUNC_CHOICE%"=="2" goto RUN_RV
if /I "%FUNC_CHOICE%"=="A" goto RUN_ALL
if /I "%FUNC_CHOICE%"=="3" goto RUN_ALL

echo ❌ Invalid function choice.
pause
exit /b 1

:RUN_ORDER
echo [ORDER] Running...
%BASE_CMD% %PLATFORM_ARG%
goto END_RUN

:RUN_RV
echo [RV] Running...
%BASE_RV_CMD% %PLATFORM_ARG%
goto END_RUN

:RUN_ALL
echo [ALL] Step 1/2: ORDER
%BASE_CMD% %PLATFORM_ARG%
echo.
echo [ALL] Step 2/2: RV
%BASE_RV_CMD% %PLATFORM_ARG%
goto END_RUN

:END_RUN
echo.
echo ------------------------------------------
echo Sync finished.
echo Log saved in: logs\sync_*.txt
echo Opening logs folder...
explorer "%~dp0logs"
echo.
pause
