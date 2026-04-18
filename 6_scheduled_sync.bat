@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

:: ─────────────────────────────────────────────
:: TRCloud Scheduled Sync — D-1 (ไม่ต้องกด)
:: รันโดย Task Scheduler ทุกคืน/เช้า
:: ─────────────────────────────────────────────

cd /d "%~dp0"

:: ── Auto-update จาก GitHub ──────────────────
git -C "%~dp0" pull --ff-only --quiet 2>nul && (
    echo [git] Updated from GitHub
) || (
    echo [git] Pull skipped ^(no git / no remote / local changes^)
)

:: คำนวณวานนี้ (D-1) ด้วย PowerShell
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).AddDays(-1).ToString('yyyy-MM-dd')"') do set YESTERDAY=%%d

echo.
echo ============================================================
echo  TRCloud Auto Sync  [%date% %time%]
echo  Target date: %YESTERDAY%
echo ============================================================
echo.

:: ── ORDER sync ──────────────────────────────
echo [ORDER] เริ่ม sync ORDER...
echo Start: %time%
python trcloud_sync_browser.py --start-date %YESTERDAY% --end-date %YESTERDAY%
echo End  : %time%
echo.

:: ── RV sync ─────────────────────────────────
echo [RV] เริ่ม sync RECEIPT [RV]...
echo Start: %time%
python trcloud_sync_browser.py --rv --start-date %YESTERDAY% --end-date %YESTERDAY%
echo End  : %time%
echo.

echo ============================================================
echo  Sync เสร็จสิ้น  [%date% %time%]
echo ============================================================
echo.

endlocal
