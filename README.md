# TRCloud Sync Browser

Playwright browser automation for syncing marketplace orders (Shopee, TikTok, Lazada) into TRCloud ERP.

## Features

- **ORDER sync** — Sync document, items, and full tax per shop per day
- **RV sync** — Sync payment receipts (RECEIPT [RV])
- **Scheduled auto-sync** — Fully automated D-1 sync via Task Scheduler
- **Gmail notification** — Email alert after each run (success/fail summary)
- **Auto-update** — BAT files pull latest code from GitHub on open
- **Date range** — Single browser session across multiple days

## Requirements

- Windows 10 / 11
- Python 3.12+
- Git
- Playwright (Chromium)

## Installation

```bash
# 1. Clone
git clone https://github.com/deknon/tr_sync.git
cd tr_sync

# 2. Install Playwright
pip install playwright
playwright install chromium

# 3. Gmail config
copy config.example.json config.json
# Edit config.json — fill in gmail_sender, gmail_password (App Password), gmail_receiver

# 4. Login session (one-time per machine)
python trcloud_sync_browser.py --setup
```

## Usage

### Interactive menu (manual)
```
5_sync_menu_browser.bat
```
Select function, platform, date range, and visible mode.

### Scheduled auto-sync (automated D-1)
```
6_scheduled_sync.bat
```
Calculates yesterday automatically. Runs ORDER then RV. Sends one combined email.

### Command line

```bash
# ORDER — all shops today
python trcloud_sync_browser.py

# ORDER — date range
python trcloud_sync_browser.py --start-date 2026-04-01 --end-date 2026-04-07

# ORDER — one platform
python trcloud_sync_browser.py --platform shopee

# ORDER — one shop
python trcloud_sync_browser.py --shop 1

# RV — date range
python trcloud_sync_browser.py --rv --start-date 2026-04-01 --end-date 2026-04-01

# Debug (visible browser)
python trcloud_sync_browser.py --visible --shop 1
```

## Shops

Managed in [`shops.json`](shops.json) — add or remove shops without editing Python code.

```json
{ "api_id": 1, "name": "Shopee Ugreen", "platform": "shopee" }
```

## Files

| File | Description |
|---|---|
| `trcloud_sync_browser.py` | Main automation script |
| `shops.json` | Shop list (Shopee / TikTok / Lazada) |
| `config.json` | Gmail credentials — **gitignored, never committed** |
| `config.example.json` | Credentials template for new machines |
| `5_sync_menu_browser.bat` | Interactive menu launcher |
| `6_scheduled_sync.bat` | Fully automated D-1 sync |
| `docs/` | Documentation and team guides |
| `logs/` | Run logs and error screenshots — gitignored |

## CLI Flags

| Flag | Description |
|---|---|
| `--setup` | Login and save session (first run) |
| `--rv` | RV sync mode |
| `--shop <id>` | Sync one shop by api_id |
| `--platform <name>` | Filter by shopee / tiktok / lazada |
| `--date <YYYY-MM-DD>` | Sync specific date |
| `--start-date` / `--end-date` | Date range |
| `--visible` | Show browser (debug mode) |
| `--no-notify` | Skip email notification |

## Troubleshooting

| Problem | Fix |
|---|---|
| Session expired | `python trcloud_sync_browser.py --setup` |
| Browser not opening | `playwright install chromium` |
| No email received | Check `config.json` — use App Password not regular password |
| `[git] Pull skipped` | Run `git pull` manually once to login GitHub |
| Shop sync failed | Retry with `--shop <id> --visible` to inspect |

## Docs

- [`docs/QUICK_START_TEAM.txt`](docs/QUICK_START_TEAM.txt) — Quick start for team
- [`docs/COMMAND_TEMPLATES.txt`](docs/COMMAND_TEMPLATES.txt) — Copy-paste commands
- [`docs/COMMON_ERRORS_AND_FIXES.txt`](docs/COMMON_ERRORS_AND_FIXES.txt) — Error reference
- [`docs/TEAM_GUIDE_GIT.html`](docs/TEAM_GUIDE_GIT.html) — Printable PDF team guide
- [`docs/UPDATE_DETAIL_RV.txt`](docs/UPDATE_DETAIL_RV.txt) — Changelog
