"""
TRCloud Marketplace Sync — Browser Automation (Playwright)
===========================================================
ใช้ browser automation แทน API เพื่อให้ข้อมูลแสดงผลในหน้าเว็บ TRCloud ได้ถูกต้อง

วิธีใช้งาน:
  ครั้งแรก (setup session):
    python trcloud_sync_browser.py --setup

  ทดสอบ 1 shop:
    python trcloud_sync_browser.py --shop 1

  รันทั้งหมด (วันนี้):
    python trcloud_sync_browser.py

  รันเฉพาะ platform:
    python trcloud_sync_browser.py --platform shopee

  ดู browser ขณะรัน (debug):
    python trcloud_sync_browser.py --visible

ติดตั้ง:
  pip install playwright
  playwright install chromium
"""

import asyncio
import json
import sys
import argparse
import smtplib
import ssl
import socket
from email.mime.text import MIMEText
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ Playwright ยังไม่ได้ติดตั้ง กรุณารัน:")
    print("   pip install playwright")
    print("   playwright install chromium")
    sys.exit(1)


def _configure_console_utf8():
    """Windows consoles often default to cp1252; Thai logs must not crash print()."""
    for stream in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
        if stream is None:
            continue
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass


_configure_console_utf8()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BASE_URL      = "https://gv.trcloud.co"
APP_URL       = f"{BASE_URL}/application"
SESSION_FILE  = Path(__file__).parent / "trcloud_session.json"
SHOPS_FILE    = Path(__file__).parent / "shops.json"
LOG_DIR       = Path(__file__).parent / "logs"
LOG_DIR_TEXT  = LOG_DIR / "text"
LOG_DIR_PHOTO = LOG_DIR / "photo"

RV_ENDPOINTS = {
    "tiktok": f"{APP_URL}/connector/manage-data-tiktok-rv.php?id={{shop_id}}",
    "shopee": f"{APP_URL}/connector/manage-data-shopee-rv.php?id={{shop_id}}",
    "lazada": f"{APP_URL}/connector/manage-data-lazada-rv.php?id={{shop_id}}",
}

# โหลด SO เข้า TRCloud แบบ FULL INVOICE (FULL TAX) — หน้า UI เหมือนกันทุก platform
FULL_INVOICE_ENDPOINTS = {
    "tiktok": f"{APP_URL}/connector/manage-data-tiktok-trcloud.php?id={{shop_id}}",
    "shopee": f"{APP_URL}/connector/manage-data-shopee-trcloud.php?id={{shop_id}}",
    "lazada": f"{APP_URL}/connector/manage-data-lazada-trcloud.php?id={{shop_id}}",
}

# Shopee/Lazada เท่านั้นที่มี filter "Full Tax" (1=ลูกค้าขอ ETAX, 0=บิลปกติ)
# ต้องสลับ prefix เอกสารที่หน้า manage-shop ก่อน download แต่ละกลุ่ม — TikTok ไม่มี filter นี้
SHOP_SETTINGS_ENDPOINTS = {
    "shopee": f"{APP_URL}/connector/manage-shop-shopee.php?id={{shop_id}}",
    "lazada": f"{APP_URL}/connector/manage-shop-lazada.php?id={{shop_id}}",
}
PREFIX_IV_ETAX   = "ETIV"
PREFIX_IV_NORMAL = "ONIV"

# Contact Name บนหน้า manage-shop (select: 0=Follow Platform, 1=Follow TRCLOUD Master)
# ETAX ต้องใช้ชื่อ-ที่อยู่ตามที่ลูกค้ากรอกในแพลตฟอร์ม / ปกติใช้ชื่อจาก TRCLOUD Master
CONTACT_NAME_FOLLOW_PLATFORM = "0"
CONTACT_NAME_FOLLOW_MASTER   = "1"

# ─────────────────────────────────────────────
# SHOPS — โหลดจาก shops.json (fallback inline)
# ─────────────────────────────────────────────
_SHOPS_DEFAULT = [
    {"api_id": 1,  "name": "Shopee Ugreen",      "platform": "shopee"},
    {"api_id": 6,  "name": "Shopee Fantech Mall", "platform": "shopee"},
    {"api_id": 8,  "name": "Shopee Fantech Plus", "platform": "shopee"},
    {"api_id": 9,  "name": "Shopee UgreenGV+",    "platform": "shopee"},
    {"api_id": 10, "name": "Shopee Philips",      "platform": "shopee"},
    {"api_id": 12, "name": "Shopee Boya",         "platform": "shopee"},
    {"api_id": 14, "name": "Shopee GV",           "platform": "shopee"},
    {"api_id": 15, "name": "Shopee JoyRoom",      "platform": "shopee"},
    {"api_id": 20, "name": "Shopee Nas",          "platform": "shopee"},
    {"api_id": 3,  "name": "Tiktok Ugreen",       "platform": "tiktok"},
    {"api_id": 4,  "name": "Tiktok Fantech",      "platform": "tiktok"},
    {"api_id": 5,  "name": "Tiktok Boya",         "platform": "tiktok"},
    {"api_id": 7,  "name": "Tiktok Philips",      "platform": "tiktok"},
    {"api_id": 2,  "name": "Lazada GV",           "platform": "lazada"},
    {"api_id": 16, "name": "Lazada Fantech",      "platform": "lazada"},
    {"api_id": 17, "name": "Lazada Ug mall",      "platform": "lazada"},
    {"api_id": 18, "name": "Lazada Philips",      "platform": "lazada"},
    {"api_id": 19, "name": "Lazada Boya",         "platform": "lazada"},
]


def load_shops() -> list:
    if SHOPS_FILE.exists():
        try:
            with open(SHOPS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠ ไม่สามารถโหลด shops.json: {e} — ใช้ค่า default")
    return _SHOPS_DEFAULT


SHOPS = load_shops()

# ─────────────────────────────────────────────
# COMPLETE SIGNAL (per-session, ไม่ใช้ global)
# ─────────────────────────────────────────────
class _Signal:
    """asyncio.Event สำหรับจับสัญญาณ 'Complete' — สร้างใหม่ต่อ browser session"""
    __slots__ = ("event",)

    def __init__(self):
        self.event: asyncio.Event = asyncio.Event()

    def prepare(self):
        self.event = asyncio.Event()

    def set(self):
        self.event.set()

    def is_set(self) -> bool:
        return self.event.is_set()

    def clear(self):
        self.event.clear()


# ─────────────────────────────────────────────
# LOGGER (console + file)
# ─────────────────────────────────────────────
_log_file = None
_log_mode = "RUN"
_pc_name  = socket.gethostname()


def cleanup_old_logs(days: int = 7):
    """Delete text and photo log files older than `days` days."""
    cutoff = datetime.now().timestamp() - days * 86400
    for d in (LOG_DIR_TEXT, LOG_DIR_PHOTO):
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and f.stat().st_mtime < cutoff:
                    try:
                        f.unlink()
                    except Exception:
                        pass


def init_log(mode: str = "RUN"):
    """Create log file for this run and clean up logs older than 7 days."""
    global _log_file, _log_mode
    _log_mode = mode.upper()
    LOG_DIR_TEXT.mkdir(parents=True, exist_ok=True)
    cleanup_old_logs()
    run_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = LOG_DIR_TEXT / f"run_{_log_mode}_{_pc_name}_{run_ts}.txt"
    _log_file = open(log_path, "w", encoding="utf-8")
    log(f"Log file: {log_path.name}")
    log(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("="*55)
    return log_path


def close_log():
    global _log_file
    if _log_file:
        _log_file.close()
        _log_file = None


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)
    if _log_file:
        _log_file.write(line + "\n")
        _log_file.flush()


# ─────────────────────────────────────────────
# GMAIL ALERT
# ─────────────────────────────────────────────
_CONFIG_FILE = Path(__file__).parent / "config.json"
_cfg = {}
if _CONFIG_FILE.exists():
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as _f:
            _cfg = json.load(_f)
    except Exception:
        pass

GMAIL_SENDER   = _cfg.get("gmail_sender",   "")
GMAIL_PASSWORD = _cfg.get("gmail_password", "")
GMAIL_RECEIVER = _cfg.get("gmail_receiver", "")


def notify_gmail(subject: str, body: str):
    """ส่ง email แจ้งผลผ่าน Gmail SMTP SSL — ถ้า fail จะ log warning เท่านั้น ไม่ crash"""
    try:
        receivers = [r.strip() for r in GMAIL_RECEIVER.split(",")]
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_SENDER
        msg["To"]      = GMAIL_RECEIVER

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as smtp:
            smtp.login(GMAIL_SENDER, GMAIL_PASSWORD)
            smtp.sendmail(GMAIL_SENDER, receivers, msg.as_string())
        log(f"📧 Email sent → {GMAIL_RECEIVER}")
    except Exception as e:
        log(f"⚠ Email send failed (skippable): {e}")


# ─────────────────────────────────────────────
# SESSION SETUP (รันครั้งแรกเพื่อ save cookie)
# ─────────────────────────────────────────────
async def setup_session():
    """เปิด browser ให้ user login แล้ว save session cookie"""
    log("Opening browser for login...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()
        page    = await context.new_page()

        await page.goto(f"{APP_URL}/", wait_until="networkidle")

        print("\n" + "="*50)
        print(">> กรุณา Login TRCloud ในหน้าต่าง browser ที่เปิดขึ้น")
        print(">> เมื่อ Login สำเร็จแล้ว กลับมากด Enter ที่นี่")
        print("="*50)
        input("\nกด Enter หลังจาก Login เสร็จแล้ว...")

        await context.storage_state(path=str(SESSION_FILE))
        log(f"✅ Session saved: {SESSION_FILE.name}")
        await browser.close()


# ─────────────────────────────────────────────
# MODAL HANDLER (ใช้กับทุก platform)
# ─────────────────────────────────────────────
async def _screenshot(page, label: str):
    """Save screenshot on error."""
    try:
        LOG_DIR_PHOTO.mkdir(parents=True, exist_ok=True)
        ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = LOG_DIR_PHOTO / f"run_{_log_mode}_{_pc_name}_{label}_{ts}.png"
        await page.screenshot(path=str(path))
        log(f"  📸 Screenshot: logs/photo/{path.name}")
    except Exception:
        pass


async def wait_for_modal_and_confirm(page, shop_name: str, timeout: int = 10000) -> bool:
    """
    รอ modal popup ปรากฏ → tick checkbox ทั้งหมด → กด confirm (ภายใน modal เท่านั้น)
    หมายเหตุ: หา confirm เฉพาะใน modal ที่พบ ไม่หา page-wide เพื่อไม่ให้ dismiss COMPLETE modal
    """
    try:
        modal = page.locator(
            '.modal.show, .modal[style*="display: block"], '
            '.popup-overlay, [role="dialog"]'
        ).first
        await modal.wait_for(state="visible", timeout=timeout)
        await page.wait_for_timeout(200)  # รอ animation เสร็จ

    except PlaywrightTimeout:
        log(f"    ⚡ No modal found (may run immediately)")
        return True

    # ── Tick checkbox — กด select-all (checkbox แรก) เท่านั้น ──
    try:
        checkboxes = modal.locator('input[type="checkbox"]')
        count = await checkboxes.count()

        if count == 0:
            checkboxes = page.locator('input[type="checkbox"]:visible')
            count = await checkboxes.count()

        if count > 0:
            first_cb = checkboxes.first
            is_checked = await first_cb.is_checked(timeout=3000)
            if not is_checked:
                await first_cb.check()
                await page.wait_for_timeout(100)
            log(f"    ✓ Tick checkbox ({count} item(s))")

    except Exception as e:
        log(f"    ⚠ Checkbox: {e}")

    await page.wait_for_timeout(100)

    # ── กด Confirm / Submit (ค้นหาเฉพาะใน modal เท่านั้น) ──
    confirm_candidates = [
        modal.locator("button.btn-primary, button.btn-success, button.btn-info").first,
        modal.locator("button[type='submit']").first,
        modal.locator("button:has-text('ยืนยัน'), button:has-text('Confirm'), button:has-text('Submit'), button:has-text('Sync')").first,
        modal.locator("button:has-text('ตกลง')").first,
    ]

    confirmed = False
    for btn in confirm_candidates:
        try:
            if await btn.is_visible(timeout=500):
                await btn.click()
                confirmed = True
                log(f"    ✓ Confirm clicked")
                break
        except Exception:
            continue

    if not confirmed:
        log(f"    ℹ Confirm button not found (auto-complete/self-close) — continuing")

    try:
        await modal.wait_for(state="hidden", timeout=60000)
    except PlaywrightTimeout:
        pass

    await page.wait_for_timeout(300)
    return True


async def wait_for_operation(page, timeout: int = 120000):
    """Wait for loading spinner or progress bar to disappear."""
    try:
        spinner = page.locator(
            '.loading, .spinner, .progress, '
            '[class*="loading"], [class*="spinner"]'
        ).first
        if await spinner.is_visible(timeout=3000):
            log(f"    ⏳ Waiting for loading...")
            await spinner.wait_for(state="hidden", timeout=timeout)
    except PlaywrightTimeout:
        pass
    except Exception:
        pass


def prepare_complete_event(signal: _Signal):
    """เรียกก่อน click ปุ่ม sync ทุกครั้ง เพื่อรับ dialog ที่อาจยิงเร็วมาก"""
    signal.prepare()


def calc_timeout(order_count: int) -> int:
    """
    คำนวณ timeout (ms) แบบ dynamic จากจำนวน orders
    สูตร: max(300s, 120s_base + count × 1.5s) — cap ที่ 3600s (1 ชั่วโมง)
    """
    seconds = min(int(30 + order_count * 10), 3600)
    log(f"    ⏱ Dynamic timeout: {order_count} orders → {seconds}s")
    return seconds * 1000


async def wait_for_complete_popup(page, shop_id: int, signal: _Signal, timeout: int = 120000) -> bool:
    """
    รอสัญญาณ sync เสร็จ — TRCloud มี 2 รูปแบบ:
      1. มีข้อมูลใหม่   → ยิง native dialog 'Complete'  (จับโดย handle_dialog + signal)
      2. ไม่มีข้อมูลใหม่ → แสดง DOM modal "COMPLETE - No more data!" (จับโดย DOM polling)
    """
    # ── ตรวจว่า signal มาก่อนเราเริ่มรอหรือเปล่า (race condition fix) ──
    if signal.is_set():
        log(f"    ✓ Complete (native dialog, pre-arrived 0s)")
        signal.clear()
        await page.wait_for_timeout(300)
        return True

    log(f"    Waiting for Complete signal (max {timeout//1000}s)...")
    elapsed = 0
    interval = 500

    while elapsed < timeout:
        # ── ตรวจ 1: native dialog 'Complete' ──
        if signal.is_set():
            log(f"    ✓ Complete (native dialog, {elapsed//1000}s)")
            signal.clear()
            await page.wait_for_timeout(300)
            return True

        # ── ตรวจ 2: DOM modal/popup ที่มีคำบ่งบอกว่าเสร็จสิ้น ──
        dom_result = await page.evaluate("""
            () => {
                const COMPLETE_KEYWORDS = ['complete', 'no more data', 'success', 'เสร็จ', 'สำเร็จ'];
                const SELECTORS = '.modal, .alert, .swal2-container, [class*="popup"], [class*="dialog"]';
                for (const m of document.querySelectorAll(SELECTORS)) {
                    const s = window.getComputedStyle(m);
                    if (s.display === 'none' || m.offsetHeight === 0) continue;
                    const text = (m.textContent || '').toLowerCase();
                    const matched = COMPLETE_KEYWORDS.find(k => text.includes(k));
                    if (matched) {
                        const btns = Array.from(m.querySelectorAll('button'));
                        return {
                            found: true,
                            keyword: matched,
                            snippet: m.textContent.trim().replace(/\\s+/g,' ').slice(0,80),
                            btns: btns.map(b => b.textContent.trim())
                        };
                    }
                }
                return {found: false};
            }
        """)

        if dom_result.get('found'):
            log(f"    ✓ COMPLETE DOM modal ({elapsed//1000}s) [{dom_result.get('keyword')}] — {dom_result.get('snippet')}")
            await _screenshot(page, f"shop{shop_id}_complete_popup")
            await page.evaluate("""
                () => {
                    const SELECTORS = '.modal, .alert, .swal2-container, [class*="popup"], [class*="dialog"]';
                    for (const m of document.querySelectorAll(SELECTORS)) {
                        const s = window.getComputedStyle(m);
                        if (s.display === 'none' || m.offsetHeight === 0) continue;
                        const btns = Array.from(m.querySelectorAll('button'));
                        const ok = btns.find(b =>
                            ['ok','ตกลง','close','ปิด','confirm'].includes(b.textContent.trim().toLowerCase())
                        );
                        if (ok) { ok.click(); return; }
                        if (btns.length) { btns[btns.length-1].click(); return; }
                    }
                }
            """)
            await page.wait_for_timeout(500)
            return True

        await page.wait_for_timeout(interval)
        elapsed += interval

    log(f"    ⚡ No Complete signal within {timeout//1000}s — continuing")
    return True


# ─────────────────────────────────────────────
# JS CLICK HELPER
# ─────────────────────────────────────────────
async def set_date_field(page, date_str: str) -> bool:
    """
    เซ็ตวันที่ใน Database filter ก่อนกด sync
    date_str format: YYYY-MM-DD  →  แปลงเป็น DD/MM/YYYY สำหรับ TRCloud
    """
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        trcloud_date = d.strftime("%d/%m/%Y")
    except Exception:
        return False

    result = await page.evaluate(f"""
        () => {{
            const inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="date"]'));
            const dateInput = inputs.find(inp =>
                /\\d{{2}}\\/\\d{{2}}\\/\\d{{4}}/.test(inp.value) ||
                inp.placeholder?.includes('/') ||
                inp.name?.toLowerCase().includes('date') ||
                inp.id?.toLowerCase().includes('date')
            );
            if (dateInput) {{
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(dateInput, '{trcloud_date}');
                dateInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                dateInput.dispatchEvent(new Event('change', {{bubbles: true}}));
                return dateInput.value;
            }}
            return null;
        }}
    """)
    if result:
        log(f"    📅 Date set: {result}")
        await page.wait_for_timeout(1000)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1500)
        return True
    return False


async def js_click_button(page, text: str) -> bool:
    """
    ค้นหาปุ่มที่มี text นั้น แล้วคลิกผ่าน JavaScript โดยตรง
    วิธีนี้ทำให้ jQuery/onclick handlers ทำงานได้แม้ Playwright click ปกติจะไม่ fire
    """
    result = await page.evaluate(f"""
        () => {{
            const text = {repr(text)}.toLowerCase();
            const buttons = Array.from(document.querySelectorAll('button, a.btn, input[type="button"]'));
            const btn = buttons.find(b => b.textContent.trim().toLowerCase().includes(text));
            if (btn) {{
                btn.scrollIntoView({{block: 'center'}});
                btn.click();
                return btn.textContent.trim();
            }}
            return null;
        }}
    """)
    if result:
        log(f"    JS click: '{result}'")
        return True
    return False


async def js_tick_select_all(page) -> int:
    """
    ติ๊ก checkbox 'select all' ของ main data table
    Returns: จำนวน checkboxes ที่พบ (ใช้คำนวณ dynamic timeout)
    """
    debug_info = await page.evaluate("""
        () => {
            const tables = Array.from(document.querySelectorAll('table'));
            return tables.map((t, i) => ({
                index: i,
                rows: t.querySelectorAll('tr').length,
                cbs: t.querySelectorAll('input[type="checkbox"]').length,
                textSnippet: t.textContent.replace(/\\s+/g, ' ').trim().slice(0, 80)
            }));
        }
    """)
    log(f"    Debug: found {len(debug_info)} table(s)")
    for t in debug_info[:6]:
        log(f"      table[{t['index']}] rows={t['rows']} cbs={t['cbs']} text={t['textSnippet'][:60]}")

    result = await page.evaluate("""
        () => {
            const tables = Array.from(document.querySelectorAll('table'));

            let mainTable = null;
            for (const t of tables) {
                if (t.textContent.includes('Order ID') || t.textContent.includes('Order_ID')) {
                    mainTable = t;
                    break;
                }
            }

            if (!mainTable) {
                mainTable = tables.reduce((max, t) => {
                    const cnt = t.querySelectorAll('input[type="checkbox"]').length;
                    return cnt > max.querySelectorAll('input[type="checkbox"]').length ? t : max;
                }, tables[0] || null);
            }

            if (!mainTable) return {found: false, reason: 'no table found'};

            const cbCount = mainTable.querySelectorAll('input[type="checkbox"]').length;
            const cb = mainTable.querySelector('input[type="checkbox"]');
            if (!cb) return {found: false, reason: 'no checkbox in main table', tableFound: true};

            const label = cb.closest('label') || cb.parentElement;
            const clickTarget = (label && label.tagName === 'LABEL') ? label : cb;

            if (cb.checked) {
                clickTarget.scrollIntoView({block: 'center'});
                clickTarget.click();  // uncheck ก่อน
            }
            clickTarget.scrollIntoView({block: 'center'});
            clickTarget.click();
            return {found: true, via: (label && label.tagName === 'LABEL') ? 'label' : 'input',
                    checked: cb.checked, cbCount};
        }
    """)

    if result and result.get('found'):
        count = result.get('cbCount', 0)
        log(f"    ✓ Select All clicked via={result.get('via')} cbCount={count} checked={result.get('checked')}")
        await page.wait_for_timeout(1200)
        await _screenshot(page, "after_select_all")
        return count

    log(f"    ⚠ select-all failed: {result}")
    return 0


# ─────────────────────────────────────────────
# SH STATUS FILTER HELPER
# ─────────────────────────────────────────────
async def set_sh_status_filter(page, statuses: list) -> bool:
    """
    เซ็ต SH Status multiselect filter ให้ตรงกับ statuses ที่ต้องการ
    รองรับ: select[multiple], Bootstrap multiselect, select2
    statuses เช่น ['TO_RETURN', 'RETURNED']
    """
    result = await page.evaluate("""
        (statuses) => {
            const upper = statuses.map(s => s.toUpperCase());

            // ── ค้นหา select element ที่มี option ตรงกับ statuses ──
            const selects = Array.from(document.querySelectorAll('select'));
            let target = null;
            for (const sel of selects) {
                const opts = Array.from(sel.options).map(o => o.value.toUpperCase() + '|' + o.text.toUpperCase());
                if (upper.some(s => opts.some(o => o.includes(s)))) {
                    target = sel;
                    break;
                }
            }
            if (!target) return {ok: false, reason: 'select not found'};

            // ── clear แล้ว select ตัวที่ต้องการ ──
            let matched = 0;
            for (const opt of target.options) {
                const val = (opt.value + '|' + opt.text).toUpperCase();
                opt.selected = upper.some(s => val.includes(s));
                if (opt.selected) matched++;
            }

            // fire change event
            target.dispatchEvent(new Event('change', {bubbles: true}));

            // ── Bootstrap multiselect: sync visual checkboxes ──
            const container = target.closest('.btn-group') ||
                              document.querySelector('.multiselect-container');
            if (container) {
                container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    const label = (cb.value + '|' + (cb.closest('label') || cb.parentElement || {}).textContent || '').toUpperCase();
                    cb.checked = upper.some(s => label.includes(s));
                });
            }

            return {ok: true, matched, total: target.options.length,
                    id: target.id, name: target.name};
        }
    """, statuses)

    if result.get('ok'):
        log(f"    ✓ SH Status filter: {statuses} (matched {result.get('matched')}/{result.get('total')})")
        await page.wait_for_timeout(800)
        return True

    log(f"    ⚠ SH Status filter not found: {result.get('reason')} — continuing")
    await _screenshot(page, "sh_status_filter_notfound")
    return False


# ─────────────────────────────────────────────
# STATUS ONLY SYNC (Step 1 เท่านั้น — ทุก platform)
# ─────────────────────────────────────────────
async def sync_shopee_status_only(page, shop: dict, sync_date: str = None, signal: _Signal = None) -> bool:
    shop_id = shop["api_id"]
    url = f"{APP_URL}/connector/manage-data-shopee-platform.php?id={shop_id}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        log(f"  ❌ Page load timeout: {url}")
        return False

    if sync_date:
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ Date field not found — using default date")

    log(f"  → Step 1 only: Sync Document + Status")
    try:
        prepare_complete_event(signal)
        if not await js_click_button(page, "SYNC DOCUMENT"):
            log(f"  ❌ Step 1 button not found")
            await _screenshot(page, f"error_shopee{shop_id}_status_step1")
            return False
        await page.wait_for_timeout(1000)
        await wait_for_complete_popup(page, shop_id, signal, timeout=180000)
        log(f"  ✅ Step 1 OK")
        return True
    except Exception as e:
        log(f"  ❌ Step 1 failed: {e}")
        await _screenshot(page, f"error_shopee{shop_id}_status_step1")
        return False


async def sync_tiktok_status_only(page, shop: dict, sync_date: str = None, signal: _Signal = None) -> bool:
    shop_id = shop["api_id"]
    url = f"{APP_URL}/connector/manage-data-tiktok-platform.php?id={shop_id}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        log(f"  ❌ Page load timeout: {url}")
        return False

    if sync_date:
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ Date field not found — using default date")

    log(f"  → Step 1 only: Sync Document & Items")
    try:
        prepare_complete_event(signal)
        btn1 = page.get_by_role("button", name="SYNC", exact=False).first
        await btn1.click()
        await wait_for_modal_and_confirm(page, shop["name"])
        await wait_for_operation(page)
        await wait_for_complete_popup(page, shop_id, signal, timeout=180000)
        log(f"  ✅ Step 1 OK")
        return True
    except Exception as e:
        log(f"  ❌ Step 1 failed: {e}")
        await _screenshot(page, f"error_tiktok{shop_id}_status_step1")
        return False


async def sync_lazada_status_only(page, shop: dict, sync_date: str = None, signal: _Signal = None) -> bool:
    shop_id = shop["api_id"]
    url = f"{APP_URL}/connector/manage-data-lazada-platform.php?id={shop_id}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        log(f"  ❌ Page load timeout: {url}")
        return False

    if sync_date:
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ Date field not found — using default date")

    log(f"  → Step 1 only: Sync Document")
    try:
        btn1 = page.get_by_role("button", name="SYNC DOCUMENT", exact=False)
        if not await btn1.is_visible(timeout=5000):
            btn1 = page.locator("button:has-text('SYNC')").first
        await btn1.click()
        await wait_for_modal_and_confirm(page, shop["name"])
        await wait_for_operation(page)
        log(f"  ✅ Step 1 OK")
        return True
    except Exception as e:
        log(f"  ❌ Step 1 failed: {e}")
        await _screenshot(page, f"error_lazada{shop_id}_status_step1")
        return False


SYNC_STATUS_FN = {
    "shopee": sync_shopee_status_only,
    "tiktok": sync_tiktok_status_only,
    "lazada": sync_lazada_status_only,
}


# ─────────────────────────────────────────────
# RETURN ITEM SYNC (Step 6 — Shopee only)
# ─────────────────────────────────────────────
async def sync_shopee_return_item(page, shop: dict, sync_date: str = None, signal: _Signal = None) -> bool:
    """
    Sync return items — Shopee only
    Filter SH Status: TO_RETURN, RETURNED → click Step 6
    """
    shop_id = shop["api_id"]
    url = f"{APP_URL}/connector/manage-data-shopee-platform.php?id={shop_id}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        log(f"  ❌ Page load timeout: {url}")
        return False

    if sync_date:
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ Date field not found — using default date")

    # ── เซ็ต SH Status filter ──
    log(f"  → Set SH Status: TO_RETURN, RETURNED")
    await set_sh_status_filter(page, ["TO_RETURN", "RETURNED"])

    # ── RUN เพื่อโหลดข้อมูลตาม filter ──
    log(f"  → RUN (load data)")
    try:
        run_result = await page.evaluate("""
            () => {
                const btn = document.querySelector('button.btn-lilac');
                if (btn) { btn.scrollIntoView({block:'center'}); btn.click();
                           return btn.title || btn.textContent.trim(); }
                return null;
            }
        """)
        if run_result is not None:
            log(f"    JS click: RUN ({run_result.strip()})")
            await wait_for_operation(page)
            await page.wait_for_timeout(1500)
        else:
            log(f"    ⚠ RUN button not found — continuing")
    except Exception as e:
        log(f"    ⚠ RUN: {e}")

    # ── Select All ──
    log(f"  → Select All")
    order_count = 0
    try:
        order_count = await js_tick_select_all(page)
        await page.wait_for_timeout(300)
    except Exception as e:
        log(f"    ⚠ Select All: {e}")

    # ── Step 6: RETURNED ITEMs (onclick="sync_return()") ──
    log(f"  → Step 6: RETURNED ITEMs")
    try:
        prepare_complete_event(signal)
        clicked = await page.evaluate("""
            () => {
                const btn = document.querySelector('button[onclick="sync_return()"]');
                if (btn) { btn.scrollIntoView({block:'center'}); btn.click();
                           return btn.textContent.trim(); }
                return null;
            }
        """)
        if not clicked:
            log(f"  ❌ sync_return() button not found")
            await _screenshot(page, f"error_shopee{shop_id}_return_step6_notfound")
            return False
        log(f"    JS click: {clicked}")

        await page.wait_for_timeout(1000)
        await wait_for_modal_and_confirm(page, shop["name"])
        await wait_for_complete_popup(page, shop_id, signal, timeout=calc_timeout(order_count))
        log(f"  ✅ Step 6 OK")
        return True

    except Exception as e:
        log(f"  ❌ Step 6 failed: {e}")
        await _screenshot(page, f"error_shopee{shop_id}_return_step6")
        return False


# ─────────────────────────────────────────────
# RECEIPT [RV] SYNC
# ─────────────────────────────────────────────
async def sync_receipt_rv_shop(page, shop: dict, sync_date: str, signal: _Signal) -> bool:
    platform  = shop["platform"]
    shop_id   = shop["api_id"]
    shop_name = shop["name"]

    url_tpl = RV_ENDPOINTS.get(platform)
    if not url_tpl:
        log(f"  ❌ Unsupported RV platform: {platform} (shop={shop_name})")
        return False
    url = url_tpl.format(shop_id=shop_id)

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        log(f"  ❌ Page load timeout (RV): {url}")
        return False

    log(f"  → Database date: {sync_date}")
    if not await set_date_field(page, sync_date):
        await _screenshot(page, f"error_rv_{platform}{shop_id}_set_date")
        return False

    log("  → Step 1: Sync Payment")
    try:
        prepare_complete_event(signal)
        clicked = await js_click_button(page, "SYNC PAYMENT")
        if not clicked:
            clicked = await js_click_button(page, "SYNC DOCUMENT")
        if not clicked:
            clicked = await js_click_button(page, "SYNC")
        if not clicked:
            log("  ❌ Step 1 button not found (SYNC PAYMENT / SYNC DOCUMENT / SYNC)")
            await _screenshot(page, f"error_rv_{platform}{shop_id}_step1_notfound")
            return False

        await page.wait_for_timeout(1000)
        await wait_for_modal_and_confirm(page, f"{platform} RV")
        await wait_for_operation(page)
        await wait_for_complete_popup(page, 0, signal, timeout=90000)

        log("  → RUN (refresh table after sync)")
        try:
            run_result = await page.evaluate("""
                () => {
                    const btn = document.querySelector('button.btn-lilac');
                    if (btn) {
                        btn.scrollIntoView({block: 'center'});
                        btn.click();
                        return btn.title || btn.textContent.trim();
                    }
                    return null;
                }
            """)
            if run_result is not None:
                log(f"    JS click: RUN ({run_result.strip()})")
                await wait_for_operation(page)
            else:
                log("    ⚠ RUN button not found (btn-lilac)")
        except Exception as e:
            log(f"    ⚠ RUN refresh: {e}")

        log("  ✅ Step 1 OK")
        return True

    except Exception as e:
        log(f"  ❌ Step 1 failed: {e}")
        await _screenshot(page, f"error_rv_{platform}{shop_id}_step1")
        return False


async def run_sync_receipt_rv(start_date: str, end_date: str, visible: bool = False,
                               platform: str = None, target_id: int = None,
                               no_notify: bool = False):
    """
    Sync RECEIPT [RV] เฉพาะ Step 1 — เปิด browser ครั้งเดียว วนรันทุกวัน
    """
    if not SESSION_FILE.exists():
        log("❌ No session found. Please run: python trcloud_sync_browser.py --setup")
        return

    try:
        d_start = date.fromisoformat(start_date)
        d_end   = date.fromisoformat(end_date)
    except ValueError:
        log(f"❌ Invalid date: {start_date} / {end_date}")
        return

    if d_start > d_end:
        log("❌ start-date must be <= end-date")
        return

    log_path = init_log("RV")

    if target_id is not None:
        rv_shops = [s for s in SHOPS if s["api_id"] == target_id]
    elif platform:
        rv_shops = [s for s in SHOPS if s["platform"] == platform.lower()]
    else:
        rv_shops = [s for s in SHOPS if s["platform"] in ["tiktok", "shopee", "lazada"]]

    if not rv_shops:
        log(f"❌ No shops found for RV (platform={platform}, shop={target_id})")
        close_log()
        return

    total_days = (d_end - d_start).days + 1
    total      = len(rv_shops) * total_days
    success    = 0
    failed     = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=not visible,
                slow_mo=100 if visible else 50,
            )
            context = await browser.new_context(
                storage_state=str(SESSION_FILE),
                viewport={"width": 1280, "height": 900},
            )
            page   = await context.new_page()
            signal = _Signal()

            async def handle_dialog(dialog):
                log(f"    💬 Dialog: '{dialog.message}' → OK")
                await dialog.accept()
                if "complete" in dialog.message.lower():
                    signal.set()
                    log("    ✓ Complete signal set")
            page.on("dialog", handle_dialog)

            log("Checking session...")
            await page.goto(f"{APP_URL}/", wait_until="networkidle", timeout=30000)
            if "login" in page.url.lower():
                log("❌ Session expired. Please run --setup again")
                await browser.close()
                return
            log("✅ Session valid")

            log(f"\n{'='*55}")
            log(f"RECEIPT [RV] Sync — {len(rv_shops)} shop(s) × {total_days} day(s)")
            log(f"Date range: {start_date} → {end_date}")
            log(f"{'='*55}")

            job_i   = 0
            current = d_start
            while current <= d_end:
                day_label = str(current)
                log(f"\n{'─'*55}")
                log(f"Date: {day_label}")
                log(f"{'─'*55}")

                for shop in rv_shops:
                    job_i += 1
                    log(f"\n[{job_i}/{total}] {shop['name']} ({shop['platform'].upper()}) RV — {day_label}")
                    ok = await sync_receipt_rv_shop(page, shop, day_label, signal)
                    if ok:
                        success += 1
                    else:
                        failed.append(f"{shop['name']}@{day_label}")

                current += timedelta(days=1)

            log(f"\n{'='*55}")
            log(f"Summary RV: ✅ {success}/{total} succeeded")
            if failed:
                log(f"            ❌ Failed: {', '.join(failed)}")
            log(f"{'='*55}")
            log(f"Log saved to: logs\\text\\{log_path.name}")

            if not no_notify:
                ts_done = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if failed:
                    notify_gmail(
                        f"[TRCloud RV] ❌ มี {len(failed)} รายการล้มเหลว ({ts_done})",
                        f"สรุป RV sync: {success}/{total} สำเร็จ\n\nล้มเหลว:\n" + "\n".join(f"  - {f}" for f in failed) + f"\n\nLog: logs\\text\\{log_path.name}",
                    )
                else:
                    notify_gmail(
                        f"[TRCloud RV] ✅ {success}/{total} สำเร็จ ({ts_done})",
                        f"สรุป RV sync: {success}/{total} สำเร็จทั้งหมด\n\nLog: logs\\text\\{log_path.name}",
                    )

            await browser.close()
    finally:
        close_log()


# ─────────────────────────────────────────────
# SHOPEE SYNC
# ─────────────────────────────────────────────
async def sync_shopee_shop(page, shop: dict, sync_date: str = None, signal: _Signal = None) -> bool:
    shop_id = shop["api_id"]

    url = f"{APP_URL}/connector/manage-data-shopee-platform.php?id={shop_id}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        log(f"  ❌ Page load timeout: {url}")
        return False

    if sync_date:
        log(f"  → Set date: {sync_date}")
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ Date field not found — using default date")

    # ── Step 1: SYNC DOCUMENT + STATUS ──
    log(f"  → Step 1: Sync Document + Status")
    try:
        prepare_complete_event(signal)
        if not await js_click_button(page, "SYNC DOCUMENT"):
            log(f"  ❌ Step 1 button not found")
            await _screenshot(page, f"error_shopee{shop_id}_step1_notfound")
            return False

        await page.wait_for_timeout(1000)
        await wait_for_complete_popup(page, shop_id, signal, timeout=180000)
        log(f"  ✅ Step 1 OK")

    except Exception as e:
        log(f"  ❌ Step 1 failed: {e}")
        await _screenshot(page, f"error_shopee{shop_id}_step1")
        return False

    # ── Tick Select All (Step 2) ──
    log(f"  → Tick Select All")
    order_count = 0
    try:
        order_count = await js_tick_select_all(page)
        log(f"    {'✓ Select All done' if order_count else '⚠ No checkbox found — proceeding to Step 2'}")
        await page.wait_for_timeout(200)
    except Exception as e:
        log(f"    ⚠ Select All: {e}")

    # ── Step 2: SYNC ITEMs ──
    log(f"  → Step 2: Sync Items")
    try:
        prepare_complete_event(signal)
        if not await js_click_button(page, "SYNC ITEMs"):
            log(f"  ❌ Step 2 button not found")
            await _screenshot(page, f"error_shopee{shop_id}_step2_notfound")
            return False

        await page.wait_for_timeout(1000)
        await wait_for_complete_popup(page, shop_id, signal, timeout=calc_timeout(order_count))
        log(f"  ✅ Step 2 OK")

    except Exception as e:
        log(f"  ❌ Step 2 failed: {e}")
        await _screenshot(page, f"error_shopee{shop_id}_step2")
        return False

    # ── RUN refresh before Step 3 ──
    log(f"  → RUN refresh before Step 3")
    try:
        run_result = await page.evaluate("""
            () => {
                const btn = document.querySelector('button.btn-lilac');
                if (btn) {
                    btn.scrollIntoView({block: 'center'});
                    btn.click();
                    return btn.title || btn.textContent.trim();
                }
                return null;
            }
        """)
        if run_result is not None:
            log(f"    JS click: RUN ({run_result.strip()})")
            await page.wait_for_timeout(2000)
        else:
            log(f"    ⚠ RUN button not found (btn-lilac) — skipping refresh")
    except Exception as e:
        log(f"    ⚠ RUN refresh: {e}")

    # ── Tick Select All (Step 3) ──
    log(f"  → Tick Select All (Step 3)")
    order_count_s3 = 0
    try:
        order_count_s3 = await js_tick_select_all(page)
        log(f"    {'✓ Select All done' if order_count_s3 else '⚠ No checkbox found — proceeding to Step 3'}")
        await page.wait_for_timeout(200)
    except Exception as e:
        log(f"    ⚠ Select All: {e}")

    # ── Step 3: FULL TAX ──
    log(f"  → Step 3: Full Tax")
    try:
        prepare_complete_event(signal)
        if not await js_click_button(page, "FULL TAX"):
            log(f"  ❌ Step 3 button not found (FULL TAX)")
            await _screenshot(page, f"error_shopee{shop_id}_step3_notfound")
            return False

        await page.wait_for_timeout(1000)
        await wait_for_complete_popup(page, shop_id, signal, timeout=calc_timeout(order_count_s3))
        log(f"  ✅ Step 3 OK")

    except Exception as e:
        log(f"  ❌ Step 3 failed: {e}")
        await _screenshot(page, f"error_shopee{shop_id}_step3")
        return False

    # ── FULL INVOICE (โหลด SO เข้า TRCloud) ──
    if not await sync_full_invoice_step(page, shop, sync_date or str(date.today()), signal):
        return False

    return True


# ─────────────────────────────────────────────
# FULL INVOICE (โหลด SO เข้า TRCloud — FULL TAX)
# ─────────────────────────────────────────────
async def _safe_goto(page, url: str, timeout: int = 30000, retries: int = 2) -> bool:
    """
    page.goto ที่ทน 'interrupted by another navigation' — เกิดขึ้นเมื่อ Save [F2] ที่หน้า
    manage-shop ยิง redirect ของตัวเองอยู่ ตอนที่เรา goto ไปหน้าอื่นพร้อมกันพอดี (race)
    """
    for attempt in range(retries + 1):
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            return True
        except PlaywrightTimeout:
            if attempt == retries:
                return False
        except Exception as e:
            if attempt == retries:
                return False
            log(f"    ⚠ Navigation interrupted, retry {attempt + 1}/{retries}: {str(e).splitlines()[0]}")
            await page.wait_for_timeout(1000)
    return False


async def _run_report_and_count(page) -> int:
    """กด RUN (generate_report) แล้วนับจำนวนแถวใน main-table output"""
    try:
        run_result = await page.evaluate("""
            () => {
                const btn = document.querySelector('button.btn-lilac');
                if (btn) { btn.scrollIntoView({block:'center'}); btn.click();
                           return btn.title || btn.textContent.trim(); }
                return null;
            }
        """)
        if run_result is not None:
            log(f"    JS click: RUN ({run_result.strip()})")
        else:
            log(f"    ⚠ RUN button not found — continuing")
        await wait_for_operation(page)
        await page.wait_for_timeout(1500)
    except Exception as e:
        log(f"    ⚠ RUN: {e}")

    # main-table แสดงผล report ทั้งหมด ไม่มี checkbox ต่อแถว (sync ทีเดียวทั้ง batch)
    # นับจำนวนแถวจริงเพื่อคำนวณ timeout — js_tick_select_all คืน checkbox count ของ table
    # ซึ่งไม่สัมพันธ์กับจำนวนออเดอร์ในหน้านี้ (บาง platform ไม่มี checkbox ต่อแถวเลย)
    return await page.evaluate("""
        () => document.querySelector('#main-table tbody[name=output]')?.querySelectorAll('tr').length || 0
    """)


async def _set_full_tax_filter(page, value: str) -> bool:
    """value: '1' (Full Tax/ETAX) หรือ '0' (ปกติ) — คืน False ถ้าไม่มี filter นี้ในหน้า (เช่น TikTok)"""
    return bool(await page.evaluate("""
        (value) => {
            const sel = document.getElementById('full_tax');
            if (!sel) return false;
            sel.value = value;
            sel.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }
    """, value))


async def _full_invoice_download(page, shop: dict, order_count: int, signal: _Signal) -> bool:
    """Select All แล้วกด FULL TAX DOWNLOAD to TRCLOUD (sync_trcloud) — ใช้ order_count คำนวณ timeout"""
    platform = shop["platform"]
    shop_id  = shop["api_id"]
    name     = shop["name"]

    log(f"  → FULL INVOICE: Select All")
    try:
        await js_tick_select_all(page)
        await page.wait_for_timeout(300)
    except Exception as e:
        log(f"    ⚠ Select All: {e}")

    log(f"  → FULL TAX DOWNLOAD to TRCLOUD")
    try:
        prepare_complete_event(signal)
        clicked = await page.evaluate("""
            () => {
                const btn = document.querySelector('button[onclick="sync_trcloud()"]');
                if (btn) { btn.scrollIntoView({block:'center'}); btn.click();
                           return btn.textContent.trim(); }
                return null;
            }
        """)
        if not clicked:
            log(f"  ❌ sync_trcloud() button not found")
            await _screenshot(page, f"error_{platform}{shop_id}_full_invoice_notfound")
            return False
        log(f"    JS click: {clicked}")

        await page.wait_for_timeout(1000)
        await wait_for_modal_and_confirm(page, name)
        await wait_for_complete_popup(page, shop_id, signal, timeout=calc_timeout(order_count))
        log(f"  ✅ FULL INVOICE OK")
        return True

    except Exception as e:
        log(f"  ❌ FULL INVOICE failed: {e}")
        await _screenshot(page, f"error_{platform}{shop_id}_full_invoice")
        return False


async def get_shop_invoice_settings(page, platform: str, shop_id: int):
    """อ่านค่า Prefix [Full Tax] (prefix_iv) + Contact Name (contact_name) ปัจจุบันจากหน้า manage-shop"""
    url_tpl = SHOP_SETTINGS_ENDPOINTS.get(platform)
    if not url_tpl:
        return None
    if not await _safe_goto(page, url_tpl.format(shop_id=shop_id)):
        log(f"    ❌ Page load timeout (manage-shop, read settings)")
        return None
    return await page.evaluate("""
        () => {
            const iv = document.querySelector('input[name=prefix_iv]');
            const cn = document.querySelector('select[name=contact_name]');
            return {prefix_iv: iv ? iv.value : null, contact_name: cn ? cn.value : null};
        }
    """)


async def set_shop_invoice_settings(page, platform: str, shop_id: int, prefix_value: str, contact_name_value: str) -> bool:
    """
    ตั้งค่า Prefix [Full Tax] (prefix_iv, text) + Contact Name (contact_name, select)
    แล้วกด Save [F2] — ต้องอยู่ที่หน้า manage-shop อยู่แล้ว
    """
    url_tpl = SHOP_SETTINGS_ENDPOINTS.get(platform)
    if not url_tpl:
        return False
    if not await _safe_goto(page, url_tpl.format(shop_id=shop_id)):
        log(f"    ❌ Page load timeout (manage-shop, set settings)")
        return False

    fields_set = await page.evaluate("""
        ([prefixValue, contactValue]) => {
            const iv = document.querySelector('input[name=prefix_iv]');
            const cn = document.querySelector('select[name=contact_name]');
            if (!iv || !cn) return false;
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(iv, prefixValue);
            iv.dispatchEvent(new Event('input', {bubbles: true}));
            iv.dispatchEvent(new Event('change', {bubbles: true}));
            cn.value = contactValue;
            cn.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }
    """, [prefix_value, contact_name_value])
    if not fields_set:
        log(f"    ⚠ prefix_iv / contact_name field not found")
        return False

    saved = await page.evaluate("""
        () => {
            const a = Array.from(document.querySelectorAll('a')).find(
                x => (x.getAttribute('onclick') || '').includes('save_function')
            );
            if (a) { a.click(); return true; }
            return false;
        }
    """)
    if not saved:
        log(f"    ⚠ Save [F2] button not found")
        return False

    await page.wait_for_timeout(1500)
    log(f"    ✓ prefix_iv → {prefix_value}, contact_name → {contact_name_value} (saved)")
    return True


async def sync_full_invoice_step(page, shop: dict, sync_date: str, signal: _Signal) -> bool:
    """
    โหลด SO แบบ FULL INVOICE (ปุ่ม "FULL TAX DOWNLOAD to TRCLOUD" / sync_trcloud())
    รันต่อจาก sync order ของวันนั้นเสร็จแล้ว

    TikTok: ไม่มี filter "Full Tax" — download รวมทีเดียว
    Shopee/Lazada: มี filter "Full Tax" (1=ลูกค้าขอ ETAX, 0=บิลปกติ) ซึ่งต้องใช้ prefix
    เอกสาร (ETIV/ONIV) และ Contact Name (Follow Platform/Follow TRCLOUD Master) ต่างกัน —
    ต้อง sync แยก batch ตาม filter และสลับ setting ที่หน้า manage-shop ก่อน download
    แต่ละ batch แล้วสลับกลับเป็นค่า default (ONIV / Follow TRCLOUD Master) เมื่อจบ
    """
    platform = shop["platform"]
    shop_id  = shop["api_id"]

    url_tpl = FULL_INVOICE_ENDPOINTS.get(platform)
    if not url_tpl:
        return True  # platform นี้ยังไม่รองรับ FULL INVOICE — ข้าม ไม่ถือว่า fail

    url = url_tpl.format(shop_id=shop_id)
    if not await _safe_goto(page, url):
        log(f"  ❌ Page load timeout (FULL INVOICE): {url}")
        return False

    log(f"  → FULL INVOICE: Set date: {sync_date}")
    if not await set_date_field(page, sync_date):
        log(f"    ⚠ Date field not found — using default date")

    if platform not in SHOP_SETTINGS_ENDPOINTS:
        log(f"  → FULL INVOICE: RUN (generate report)")
        order_count = await _run_report_and_count(page)
        log(f"    Report rows: {order_count}")
        if order_count == 0:
            log(f"  ✅ FULL INVOICE: no orders for {sync_date} — skip")
            return True
        return await _full_invoice_download(page, shop, order_count, signal)

    # ── Shopee/Lazada: แยก batch ตาม Full Tax filter (ETAX ก่อน แล้วค่อยปกติ) ──
    ETAX_SETTINGS   = {"prefix": PREFIX_IV_ETAX,   "contact_name": CONTACT_NAME_FOLLOW_PLATFORM}
    NORMAL_SETTINGS = {"prefix": PREFIX_IV_NORMAL, "contact_name": CONTACT_NAME_FOLLOW_MASTER}

    left_on_etax_settings = False
    for tax_flag, target, label in [("1", ETAX_SETTINGS, "ETAX"), ("0", NORMAL_SETTINGS, "Normal")]:
        log(f"  → FULL INVOICE: Filter Full Tax = {tax_flag} ({label})")
        if not await _set_full_tax_filter(page, tax_flag):
            log(f"    ⚠ Full Tax filter not found — fallback เป็น single batch")
            order_count = await _run_report_and_count(page)
            if order_count == 0:
                return True
            return await _full_invoice_download(page, shop, order_count, signal)

        order_count = await _run_report_and_count(page)
        log(f"    Report rows ({label}): {order_count}")
        if order_count == 0:
            log(f"    No {label} orders for {sync_date} — skip")
            continue

        current = await get_shop_invoice_settings(page, platform, shop_id)
        if current is None:
            log(f"  ❌ Failed to read manage-shop settings for {label}")
            return False
        needs_update = (current["prefix_iv"] != target["prefix"] or current["contact_name"] != target["contact_name"])
        if needs_update:
            log(f"    → Settings → prefix={target['prefix']}, contact_name={target['contact_name']} (manage-shop)")
            if not await set_shop_invoice_settings(page, platform, shop_id, target["prefix"], target["contact_name"]):
                log(f"  ❌ Failed to update manage-shop settings for {label}")
                return False
            left_on_etax_settings = (label == "ETAX")
        else:
            log(f"    ✓ Settings already prefix={target['prefix']}, contact_name={target['contact_name']}")
            left_on_etax_settings = False

        # get/set_shop_invoice_settings navigate ออกไปหน้า manage-shop เสมอ — ต้องกลับมาตั้ง
        # date + filter + RUN ใหม่ทุกครั้งไม่ว่าจะอัพเดต settings หรือไม่ก็ตาม
        if not await _safe_goto(page, url):
            log(f"  ❌ Page load timeout (FULL INVOICE, re-nav): {url}")
            return False
        await set_date_field(page, sync_date)
        await _set_full_tax_filter(page, tax_flag)
        order_count = await _run_report_and_count(page)

        if not await _full_invoice_download(page, shop, order_count, signal):
            return False

    if left_on_etax_settings:
        # จบ loop ด้วย settings ของ ETAX ค้างไว้ (เช่นวันนั้นไม่มี Normal orders เลย) — สลับกลับให้ปลอดภัย
        log(f"  → Reset manage-shop settings back to Normal (safety)")
        if not await set_shop_invoice_settings(page, platform, shop_id, NORMAL_SETTINGS["prefix"], NORMAL_SETTINGS["contact_name"]):
            log(f"  ⚠ Could not reset settings — กรุณาเช็ค manage-shop settings ด้วยตนเอง")

    return True


# ─────────────────────────────────────────────
# TIKTOK SYNC
# ─────────────────────────────────────────────
async def sync_tiktok_shop(page, shop: dict, sync_date: str = None, signal: _Signal = None) -> bool:
    shop_id = shop["api_id"]
    name    = shop["name"]

    url = f"{APP_URL}/connector/manage-data-tiktok-platform.php?id={shop_id}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        log(f"  ❌ Page load timeout: {url}")
        return False

    if sync_date:
        log(f"  → Set date: {sync_date}")
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ Date field not found — using default date")

    # ── Step 1: SYNC DOCUMENT & ITEMs ──
    log(f"  → Step 1: Sync Document & Items")
    try:
        prepare_complete_event(signal)
        btn1 = page.get_by_role("button", name="SYNC", exact=False).first
        await btn1.click()
        await wait_for_modal_and_confirm(page, name)
        await wait_for_operation(page)
        await wait_for_complete_popup(page, shop_id, signal, timeout=180000)
        log(f"  ✅ Step 1 OK")

    except Exception as e:
        log(f"  ❌ Step 1 failed: {e}")
        await _screenshot(page, f"error_tiktok{shop_id}_step1")
        return False

    # ── Step 2: FULL INVOICE (โหลด SO เข้า TRCloud) ──
    if not await sync_full_invoice_step(page, shop, sync_date or str(date.today()), signal):
        return False

    return True


# ─────────────────────────────────────────────
# LAZADA SYNC
# ─────────────────────────────────────────────
async def sync_lazada_shop(page, shop: dict, sync_date: str = None, signal: _Signal = None) -> bool:
    shop_id = shop["api_id"]
    name    = shop["name"]

    url = f"{APP_URL}/connector/manage-data-lazada-platform.php?id={shop_id}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        log(f"  ❌ Page load timeout: {url}")
        return False

    if sync_date:
        log(f"  → Set date: {sync_date}")
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ Date field not found — using default date")

    # ── Step 1: SYNC DOCUMENT ──
    log(f"  → Step 1: Sync Document")
    try:
        btn1 = page.get_by_role("button", name="SYNC DOCUMENT", exact=False)
        if not await btn1.is_visible(timeout=5000):
            btn1 = page.locator("button:has-text('SYNC')").first

        await btn1.click()
        await wait_for_modal_and_confirm(page, name)
        await wait_for_operation(page)
        log(f"  ✅ Step 1 OK")

    except Exception as e:
        log(f"  ❌ Step 1 failed: {e}")
        await _screenshot(page, f"error_lazada{shop_id}_step1")
        return False

    # ── Step 3: SYNC DETAIL ──
    # Lazada ไม่ยิง Complete dialog/modal หลัง sync — ใช้ wait_for_operation แทน
    log(f"  → Step 3: Sync Detail")
    try:
        result = await page.evaluate("""() => {
            const btn = document.querySelector('button[onclick="sync_detail()"]');
            if (btn) { btn.scrollIntoView({block:'center'}); btn.click();
                       return btn.textContent.trim(); }
            return null;
        }""")
        if not result:
            log(f"  ❌ SYNC DETAIL button not found (sync_detail)")
            await _screenshot(page, f"error_lazada{shop_id}_step3_notfound")
            return False

        log(f"    Clicked: {result}")
        await wait_for_modal_and_confirm(page, name)
        await wait_for_operation(page)
        log(f"  ✅ Step 3 OK")

    except Exception as e:
        log(f"  ❌ Step 3 failed: {e}")
        await _screenshot(page, f"error_lazada{shop_id}_step3")
        return False

    # ── FULL INVOICE (โหลด SO เข้า TRCloud) ──
    if not await sync_full_invoice_step(page, shop, sync_date or str(date.today()), signal):
        return False

    return True


# ─────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────
SYNC_FN = {
    "shopee": sync_shopee_shop,
    "tiktok": sync_tiktok_shop,
    "lazada": sync_lazada_shop,
}


# ─────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────
async def run_sync(target_id: int = None, platform: str = None, visible: bool = False,
                   sync_date: str = None, start_date: str = None, end_date: str = None,
                   no_notify: bool = False):
    """
    เปิด browser ครั้งเดียว วนรันทุก shop ทุกวันในช่วงที่กำหนด
    target_id  : รัน shop เดียว (api_id)
    platform   : รันทุก shop ของ platform นั้น
    visible    : True = เห็น browser / False = headless
    sync_date  : วันเดียว (YYYY-MM-DD) — ถ้าไม่ระบุใช้วันนี้
    start_date / end_date : ช่วงวัน (เปิด browser ครั้งเดียว)
    """
    if not SESSION_FILE.exists():
        log("❌ No session found. Please run: python trcloud_sync_browser.py --setup")
        return

    # ── กำหนดช่วงวันที่ ──
    if start_date and end_date:
        try:
            d_start = date.fromisoformat(start_date)
            d_end   = date.fromisoformat(end_date)
        except ValueError as e:
            log(f"❌ Invalid date: {e}")
            return
        if d_start > d_end:
            log("❌ start-date must be <= end-date")
            return
    elif sync_date:
        try:
            d_start = d_end = date.fromisoformat(sync_date)
        except ValueError as e:
            log(f"❌ Invalid date: {e}")
            return
    else:
        d_start = d_end = date.today()

    total_days = (d_end - d_start).days + 1

    log_path = init_log("ORDER")

    # ── เลือก shops ──
    if target_id is not None:
        shops = [s for s in SHOPS if s["api_id"] == target_id]
        if not shops:
            log(f"❌ Shop id={target_id} not found")
            close_log()
            return
    elif platform is not None:
        shops = [s for s in SHOPS if s["platform"] == platform.lower()]
        if not shops:
            log(f"❌ No shops found for platform={platform}")
            close_log()
            return
    else:
        shops = SHOPS

    total   = len(shops) * total_days
    success = 0
    failed  = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=not visible,
                slow_mo=100 if visible else 50,
            )
            context = await browser.new_context(
                storage_state=str(SESSION_FILE),
                viewport={"width": 1280, "height": 900},
            )
            page   = await context.new_page()
            signal = _Signal()

            async def handle_dialog(dialog):
                log(f"    💬 Dialog: '{dialog.message}' → OK")
                await dialog.accept()
                if 'complete' in dialog.message.lower():
                    signal.set()
                    log(f"    ✓ Complete signal set")
            page.on("dialog", handle_dialog)

            log("Checking session...")
            await page.goto(f"{APP_URL}/", wait_until="networkidle", timeout=30000)
            if "login" in page.url.lower():
                log("❌ Session expired. Please run --setup again")
                await browser.close()
                return
            log("✅ Session valid")

            log(f"\n{'='*55}")
            log(f"TRCloud Browser Sync — {len(shops)} shop(s) × {total_days} day(s)")
            if total_days > 1:
                log(f"Date range: {d_start} → {d_end}")
            log(f"{'='*55}")

            job_i   = 0
            current = d_start
            while current <= d_end:
                if total_days > 1:
                    log(f"\n{'─'*55}")
                    log(f"Date: {current}")
                    log(f"{'─'*55}")

                for shop in shops:
                    job_i += 1
                    log(f"\n[{job_i}/{total}] {shop['name']} ({shop['platform'].upper()})")
                    fn = SYNC_FN.get(shop["platform"])
                    if fn is None:
                        log(f"  ⚠ Unsupported platform: {shop['platform']}")
                        continue

                    ok = await fn(page, shop, sync_date=str(current), signal=signal)
                    if ok:
                        success += 1
                    else:
                        label = f"{shop['name']}@{current}" if total_days > 1 else shop["name"]
                        failed.append(label)

                current += timedelta(days=1)

            log(f"\n{'='*55}")
            log(f"Summary: ✅ {success}/{total} succeeded")
            if failed:
                log(f"         ❌ Failed: {', '.join(failed)}")
            log(f"{'='*55}")
            log(f"Log saved to: logs\\text\\{log_path.name}")

            if not no_notify:
                ts_done = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if failed:
                    notify_gmail(
                        f"[TRCloud ORDER] ❌ มี {len(failed)} รายการล้มเหลว ({ts_done})",
                        f"สรุป ORDER sync: {success}/{total} สำเร็จ\n\nล้มเหลว:\n" + "\n".join(f"  - {f}" for f in failed) + f"\n\nLog: logs\\text\\{log_path.name}",
                    )
                else:
                    notify_gmail(
                        f"[TRCloud ORDER] ✅ {success}/{total} สำเร็จ ({ts_done})",
                        f"สรุป ORDER sync: {success}/{total} สำเร็จทั้งหมด\n\nLog: logs\\text\\{log_path.name}",
                    )

            await browser.close()
    finally:
        close_log()


# ─────────────────────────────────────────────
# STATUS RUNNER (Step 1 only, auto D-14)
# ─────────────────────────────────────────────
async def run_sync_status(visible: bool = False, target_id: int = None,
                          platform: str = None, no_notify: bool = False,
                          lookback_days: int = 14):
    """
    Sync Step 1 เท่านั้น (อัพเดท status) — ทุก platform
    ช่วงวันที่: วันนี้ - lookback_days → วันนี้ (auto คำนวณ)
    """
    if not SESSION_FILE.exists():
        log("❌ No session found. Please run: python trcloud_sync_browser.py --setup")
        return

    d_end   = date.today() - timedelta(days=1)   # yesterday
    d_start = d_end - timedelta(days=lookback_days - 1)
    total_days = lookback_days

    log_path = init_log("STATUS")

    if target_id is not None:
        shops = [s for s in SHOPS if s["api_id"] == target_id]
    elif platform is not None:
        shops = [s for s in SHOPS if s["platform"] == platform.lower()]
    else:
        shops = SHOPS

    if not shops:
        log(f"❌ No shops found")
        close_log()
        return

    total   = len(shops) * total_days
    success = 0
    failed  = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=not visible,
                slow_mo=100 if visible else 50,
            )
            context = await browser.new_context(
                storage_state=str(SESSION_FILE),
                viewport={"width": 1280, "height": 900},
            )
            page   = await context.new_page()
            signal = _Signal()

            async def handle_dialog(dialog):
                log(f"    💬 Dialog: '{dialog.message}' → OK")
                await dialog.accept()
                if "complete" in dialog.message.lower():
                    signal.set()
            page.on("dialog", handle_dialog)

            await page.goto(f"{APP_URL}/", wait_until="networkidle", timeout=30000)
            if "login" in page.url.lower():
                log("❌ Session expired. Please run --setup again")
                await browser.close()
                return

            log(f"\n{'='*55}")
            log(f"STATUS Sync (Step 1 only) — {len(shops)} shop(s) × {total_days} day(s)")
            log(f"Date range: {d_start} → {d_end} (D-{lookback_days})")
            log(f"{'='*55}")

            job_i   = 0
            current = d_start
            while current <= d_end:
                log(f"\n{'─'*55}")
                log(f"Date: {current}")
                log(f"{'─'*55}")
                for shop in shops:
                    job_i += 1
                    log(f"\n[{job_i}/{total}] {shop['name']} ({shop['platform'].upper()})")
                    fn = SYNC_STATUS_FN.get(shop["platform"])
                    if fn is None:
                        log(f"  ⚠ Unsupported platform: {shop['platform']}")
                        continue
                    ok = await fn(page, shop, sync_date=str(current), signal=signal)
                    if ok:
                        success += 1
                    else:
                        failed.append(f"{shop['name']}@{current}")
                current += timedelta(days=1)

            log(f"\n{'='*55}")
            log(f"Summary STATUS: ✅ {success}/{total} succeeded")
            if failed:
                log(f"               ❌ Failed: {', '.join(failed)}")
            log(f"{'='*55}")
            log(f"Log saved to: logs\\text\\{log_path.name}")

            if not no_notify:
                ts_done = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if failed:
                    notify_gmail(
                        f"[TRCloud STATUS] ❌ มี {len(failed)} รายการล้มเหลว ({ts_done})",
                        f"สรุป STATUS sync: {success}/{total} สำเร็จ\nD-{lookback_days}: {d_start} → {d_end}\n\nล้มเหลว:\n" + "\n".join(f"  - {f}" for f in failed) + f"\n\nLog: logs\\text\\{log_path.name}",
                    )
                else:
                    notify_gmail(
                        f"[TRCloud STATUS] ✅ {success}/{total} สำเร็จ ({ts_done})",
                        f"สรุป STATUS sync: {success}/{total} สำเร็จทั้งหมด\nD-{lookback_days}: {d_start} → {d_end}\n\nLog: logs\\text\\{log_path.name}",
                    )

            await browser.close()
    finally:
        close_log()


# ─────────────────────────────────────────────
# RETURN ITEM RUNNER (Step 6 — Shopee only)
# ─────────────────────────────────────────────
async def run_sync_return(start_date: str, end_date: str, visible: bool = False,
                          target_id: int = None, no_notify: bool = False):
    """
    Sync return items (Step 6) — Shopee เท่านั้น
    Filter SH Status: TO_RETURN, RETURNED
    """
    if not SESSION_FILE.exists():
        log("❌ No session found. Please run: python trcloud_sync_browser.py --setup")
        return

    try:
        d_start = date.fromisoformat(start_date)
        d_end   = date.fromisoformat(end_date)
    except ValueError:
        log(f"❌ Invalid date: {start_date} / {end_date}")
        return

    if d_start > d_end:
        log("❌ start-date must be <= end-date")
        return

    log_path = init_log("RETURN")
    total_days = (d_end - d_start).days + 1

    if target_id is not None:
        shops = [s for s in SHOPS if s["api_id"] == target_id and s["platform"] == "shopee"]
    else:
        shops = [s for s in SHOPS if s["platform"] == "shopee"]

    if not shops:
        log("❌ No Shopee shops found")
        close_log()
        return

    total   = len(shops) * total_days
    success = 0
    failed  = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=not visible,
                slow_mo=100 if visible else 50,
            )
            context = await browser.new_context(
                storage_state=str(SESSION_FILE),
                viewport={"width": 1280, "height": 900},
            )
            page   = await context.new_page()
            signal = _Signal()

            async def handle_dialog(dialog):
                log(f"    💬 Dialog: '{dialog.message}' → OK")
                await dialog.accept()
                if "complete" in dialog.message.lower():
                    signal.set()
            page.on("dialog", handle_dialog)

            await page.goto(f"{APP_URL}/", wait_until="networkidle", timeout=30000)
            if "login" in page.url.lower():
                log("❌ Session expired. Please run --setup again")
                await browser.close()
                return

            log(f"\n{'='*55}")
            log(f"RETURN ITEM Sync (Step 6) — Shopee {len(shops)} shop(s) × {total_days} day(s)")
            log(f"Filter: SH Status = TO_RETURN, RETURNED")
            log(f"Date range: {start_date} → {end_date}")
            log(f"{'='*55}")

            job_i   = 0
            current = d_start
            while current <= d_end:
                log(f"\n{'─'*55}")
                log(f"Date: {current}")
                log(f"{'─'*55}")
                for shop in shops:
                    job_i += 1
                    log(f"\n[{job_i}/{total}] {shop['name']} (SHOPEE) RETURN")
                    ok = await sync_shopee_return_item(page, shop, sync_date=str(current), signal=signal)
                    if ok:
                        success += 1
                    else:
                        failed.append(f"{shop['name']}@{current}")
                current += timedelta(days=1)

            log(f"\n{'='*55}")
            log(f"Summary RETURN: ✅ {success}/{total} succeeded")
            if failed:
                log(f"               ❌ Failed: {', '.join(failed)}")
            log(f"{'='*55}")
            log(f"Log saved to: logs\\text\\{log_path.name}")

            if not no_notify:
                ts_done = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if failed:
                    notify_gmail(
                        f"[TRCloud RETURN] ❌ มี {len(failed)} รายการล้มเหลว ({ts_done})",
                        f"สรุป RETURN sync: {success}/{total} สำเร็จ\n\nล้มเหลว:\n" + "\n".join(f"  - {f}" for f in failed) + f"\n\nLog: logs\\text\\{log_path.name}",
                    )
                else:
                    notify_gmail(
                        f"[TRCloud RETURN] ✅ {success}/{total} สำเร็จ ({ts_done})",
                        f"สรุป RETURN sync: {success}/{total} สำเร็จทั้งหมด\n\nLog: logs\\text\\{log_path.name}",
                    )

            await browser.close()
    finally:
        close_log()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="TRCloud Browser Sync (Playwright)")
    parser.add_argument("--setup",        action="store_true",  help="Login และ save session (รันครั้งแรก)")
    parser.add_argument("--rv",           action="store_true",  help="Sync RECEIPT [RV] (เฉพาะ Step 1)")
    parser.add_argument("--status",       action="store_true",  help="Sync STATUS only (Step 1, auto D-14 ถึงวันนี้)")
    parser.add_argument("--return-item",  action="store_true",  dest="return_item", help="Sync RETURN ITEM (Step 6, Shopee only, TO_RETURN+RETURNED)")
    parser.add_argument("--lookback",     type=int, default=14, help="จำนวนวันย้อนหลังสำหรับ --status (default: 14)")
    parser.add_argument("--shop",         type=int,             help="Sync เฉพาะ shop id นี้")
    parser.add_argument("--platform",     choices=["shopee", "tiktok", "lazada"], help="Sync ทุก shop ของ platform")
    parser.add_argument("--visible",      action="store_true",  help="แสดง browser ขณะรัน (debug mode)")
    parser.add_argument("--date",         type=str, default=None, help="วันที่ที่ต้องการ sync เช่น 2026-03-11 (default: วันนี้)")
    parser.add_argument("--start-date",   type=str, default=None, dest="start_date", help="วันเริ่มต้น (ใช้คู่กับ --end-date)")
    parser.add_argument("--end-date",     type=str, default=None, dest="end_date",   help="วันสิ้นสุด (ใช้คู่กับ --start-date)")
    parser.add_argument("--no-notify",    action="store_true", dest="no_notify",     help="ไม่ส่ง email แจ้งผล (ใช้เมื่อ BAT จัดการ notify เอง)")
    args = parser.parse_args()

    if args.setup:
        asyncio.run(setup_session())

    elif args.status:
        asyncio.run(run_sync_status(
            visible=args.visible,
            target_id=args.shop,
            platform=args.platform,
            no_notify=args.no_notify,
            lookback_days=args.lookback,
        ))

    elif args.return_item:
        start_date = args.start_date
        end_date   = args.end_date
        if not start_date or not end_date:
            print("\nRETURN ITEM mode (Shopee only)")
            print("กรอกช่วงวันที่ (YYYY-MM-DD)")
            start_date = input("Start date: ").strip()
            end_date   = input("End date  : ").strip()
        asyncio.run(run_sync_return(
            start_date=start_date,
            end_date=end_date,
            visible=args.visible,
            target_id=args.shop,
            no_notify=args.no_notify,
        ))

    elif args.rv:
        start_date = args.start_date
        end_date   = args.end_date

        if not start_date or not end_date:
            print("\nRECEIPT [RV] mode")
            print("กรอกช่วงวันที่ (YYYY-MM-DD) เช่น 2026-04-01")
            start_date = input("Start date: ").strip()
            end_date   = input("End date  : ").strip()

        asyncio.run(run_sync_receipt_rv(
            start_date=start_date,
            end_date=end_date,
            visible=args.visible,
            platform=args.platform,
            target_id=args.shop,
            no_notify=args.no_notify,
        ))

    else:
        asyncio.run(run_sync(
            target_id=args.shop,
            platform=args.platform,
            visible=args.visible,
            sync_date=args.date,
            start_date=args.start_date,
            end_date=args.end_date,
            no_notify=args.no_notify,
        ))


if __name__ == "__main__":
    main()
