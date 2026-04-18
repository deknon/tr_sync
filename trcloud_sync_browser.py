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
BASE_URL     = "https://gv.trcloud.co"
APP_URL      = f"{BASE_URL}/application"
SESSION_FILE = Path(__file__).parent / "trcloud_session.json"
SHOPS_FILE   = Path(__file__).parent / "shops.json"
LOG_DIR      = Path(__file__).parent / "logs"

RV_ENDPOINTS = {
    "tiktok": f"{APP_URL}/connector/manage-data-tiktok-rv.php?id={{shop_id}}",
    "shopee": f"{APP_URL}/connector/manage-data-shopee-rv.php?id={{shop_id}}",
    "lazada": f"{APP_URL}/connector/manage-data-lazada-rv.php?id={{shop_id}}",
}

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


def init_log():
    """สร้าง log file สำหรับ run นี้"""
    global _log_file
    LOG_DIR.mkdir(exist_ok=True)
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"sync_{run_ts}.txt"
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
        log(f"📧 Email แจ้งผลส่งแล้ว → {GMAIL_RECEIVER}")
    except Exception as e:
        log(f"⚠ ส่ง email ไม่สำเร็จ (ข้ามได้): {e}")


# ─────────────────────────────────────────────
# SESSION SETUP (รันครั้งแรกเพื่อ save cookie)
# ─────────────────────────────────────────────
async def setup_session():
    """เปิด browser ให้ user login แล้ว save session cookie"""
    log("เปิด browser สำหรับ login...")
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
    """บันทึก screenshot เมื่อเกิด error"""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = LOG_DIR / f"{label}_{ts}.png"
        await page.screenshot(path=str(path))
        log(f"  📸 Screenshot: logs/{path.name}")
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
        log(f"    ⚡ ไม่มี modal (อาจรันทันที)")
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
            log(f"    ✓ Tick checkbox ({count} รายการ)")

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
                log(f"    ✓ กด confirm")
                break
        except Exception:
            continue

    if not confirmed:
        log(f"    ℹ ไม่พบปุ่ม confirm (auto-complete/ปิดเอง) — ดำเนินการต่อ")

    try:
        await modal.wait_for(state="hidden", timeout=60000)
    except PlaywrightTimeout:
        pass

    await page.wait_for_timeout(300)
    return True


async def wait_for_operation(page, timeout: int = 120000):
    """รอ loading spinner หรือ progress bar หาย"""
    try:
        spinner = page.locator(
            '.loading, .spinner, .progress, '
            '[class*="loading"], [class*="spinner"]'
        ).first
        if await spinner.is_visible(timeout=3000):
            log(f"    ⏳ รอ loading เสร็จ...")
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
    seconds = max(300, int(120 + order_count * 1.5))
    seconds = min(seconds, 3600)
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

    log(f"    รอ Complete signal (สูงสุด {timeout//1000}s)...")
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

    log(f"    ⚡ ไม่มี Complete signal ใน {timeout//1000}s — ดำเนินการต่อ")
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
        log(f"    📅 เซ็ตวันที่: {result}")
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
    log(f"    Debug: พบ {len(debug_info)} ตาราง")
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
        log(f"    ✓ Select All คลิกแล้ว via={result.get('via')} cbCount={count} checked={result.get('checked')}")
        await page.wait_for_timeout(1200)
        await _screenshot(page, "after_select_all")
        return count

    log(f"    ⚠ select-all ไม่สำเร็จ: {result}")
    return 0


# ─────────────────────────────────────────────
# RECEIPT [RV] SYNC
# ─────────────────────────────────────────────
async def sync_receipt_rv_shop(page, shop: dict, sync_date: str, signal: _Signal) -> bool:
    platform  = shop["platform"]
    shop_id   = shop["api_id"]
    shop_name = shop["name"]

    url_tpl = RV_ENDPOINTS.get(platform)
    if not url_tpl:
        log(f"  ❌ ไม่รองรับ RV platform: {platform} (shop={shop_name})")
        return False
    url = url_tpl.format(shop_id=shop_id)

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        log(f"  ❌ โหลดหน้า RV timeout: {url}")
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
            log("  ❌ ไม่พบปุ่ม Step 1 (SYNC PAYMENT / SYNC DOCUMENT / SYNC)")
            await _screenshot(page, f"error_rv_{platform}{shop_id}_step1_notfound")
            return False

        await page.wait_for_timeout(1000)
        await wait_for_modal_and_confirm(page, f"{platform} RV")
        await wait_for_operation(page)
        await wait_for_complete_popup(page, 0, signal, timeout=90000)

        log("  → RUN (refresh table หลัง sync)")
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
                log("    ⚠ ไม่พบปุ่ม RUN (btn-lilac)")
        except Exception as e:
            log(f"    ⚠ RUN refresh: {e}")

        log("  ✅ Step 1 OK")
        return True

    except Exception as e:
        log(f"  ❌ Step 1 ล้มเหลว: {e}")
        await _screenshot(page, f"error_rv_{platform}{shop_id}_step1")
        return False


async def run_sync_receipt_rv(start_date: str, end_date: str, visible: bool = False,
                               platform: str = None, target_id: int = None):
    """
    Sync RECEIPT [RV] เฉพาะ Step 1 — เปิด browser ครั้งเดียว วนรันทุกวัน
    """
    if not SESSION_FILE.exists():
        log("❌ ยังไม่มี session กรุณารัน: python trcloud_sync_browser.py --setup")
        return

    try:
        d_start = date.fromisoformat(start_date)
        d_end   = date.fromisoformat(end_date)
    except ValueError:
        log(f"❌ วันที่ไม่ถูกต้อง: {start_date} / {end_date}")
        return

    if d_start > d_end:
        log("❌ start-date ต้องน้อยกว่าหรือเท่ากับ end-date")
        return

    log_path = init_log()

    if target_id is not None:
        rv_shops = [s for s in SHOPS if s["api_id"] == target_id]
    elif platform:
        rv_shops = [s for s in SHOPS if s["platform"] == platform.lower()]
    else:
        rv_shops = [s for s in SHOPS if s["platform"] in ["tiktok", "shopee", "lazada"]]

    if not rv_shops:
        log(f"❌ ไม่พบ shop สำหรับ RV (platform={platform}, shop={target_id})")
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

            log("ตรวจสอบ session...")
            await page.goto(f"{APP_URL}/", wait_until="networkidle", timeout=30000)
            if "login" in page.url.lower():
                log("❌ Session หมดอายุ กรุณารัน --setup ใหม่")
                await browser.close()
                return
            log("✅ Session ใช้ได้")

            log(f"\n{'='*55}")
            log(f"RECEIPT [RV] Sync — {len(rv_shops)} shop(s) × {total_days} day(s)")
            log(f"ช่วงวันที่: {start_date} → {end_date}")
            log(f"{'='*55}")

            job_i   = 0
            current = d_start
            while current <= d_end:
                day_label = str(current)
                log(f"\n{'─'*55}")
                log(f"วันที่: {day_label}")
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
            log(f"สรุป RV: ✅ {success}/{total} สำเร็จ")
            if failed:
                log(f"         ❌ ล้มเหลว: {', '.join(failed)}")
            log(f"{'='*55}")
            log(f"Log บันทึกที่: logs\\{log_path.name}")

            ts_done = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if failed:
                notify_gmail(
                    f"[TRCloud RV] ❌ มี {len(failed)} รายการล้มเหลว ({ts_done})",
                    f"สรุป RV sync: {success}/{total} สำเร็จ\n\nล้มเหลว:\n" + "\n".join(f"  - {f}" for f in failed) + f"\n\nLog: logs\\{log_path.name}",
                )
            else:
                notify_gmail(
                    f"[TRCloud RV] ✅ {success}/{total} สำเร็จ ({ts_done})",
                    f"สรุป RV sync: {success}/{total} สำเร็จทั้งหมด\n\nLog: logs\\{log_path.name}",
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
        log(f"  ❌ โหลดหน้า timeout: {url}")
        return False

    if sync_date:
        log(f"  → เซ็ตวันที่: {sync_date}")
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ ไม่พบ date field — ใช้วันที่ default")

    # ── Step 1: SYNC DOCUMENT + STATUS ──
    log(f"  → Step 1: Sync Document + Status")
    try:
        prepare_complete_event(signal)
        if not await js_click_button(page, "SYNC DOCUMENT"):
            log(f"  ❌ ไม่พบปุ่ม Step 1")
            await _screenshot(page, f"error_shopee{shop_id}_step1_notfound")
            return False

        await page.wait_for_timeout(1000)
        await wait_for_complete_popup(page, shop_id, signal, timeout=180000)
        log(f"  ✅ Step 1 OK")

    except Exception as e:
        log(f"  ❌ Step 1 ล้มเหลว: {e}")
        await _screenshot(page, f"error_shopee{shop_id}_step1")
        return False

    # ── ติ๊ก Select All (Step 2) ──
    log(f"  → ติ๊ก Select All")
    order_count = 0
    try:
        order_count = await js_tick_select_all(page)
        log(f"    {'✓ Select All เรียบร้อย' if order_count else '⚠ ไม่พบ checkbox — ลอง Step 2 ต่อไป'}")
        await page.wait_for_timeout(200)
    except Exception as e:
        log(f"    ⚠ Select All: {e}")

    # ── Step 2: SYNC ITEMs ──
    log(f"  → Step 2: Sync Items")
    try:
        prepare_complete_event(signal)
        if not await js_click_button(page, "SYNC ITEMs"):
            log(f"  ❌ ไม่พบปุ่ม Step 2")
            await _screenshot(page, f"error_shopee{shop_id}_step2_notfound")
            return False

        await page.wait_for_timeout(1000)
        await wait_for_complete_popup(page, shop_id, signal, timeout=calc_timeout(order_count))
        log(f"  ✅ Step 2 OK")

    except Exception as e:
        log(f"  ❌ Step 2 ล้มเหลว: {e}")
        await _screenshot(page, f"error_shopee{shop_id}_step2")
        return False

    # ── RUN refresh ก่อน Step 3 ──
    log(f"  → RUN refresh ก่อน Step 3")
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
            log(f"    ⚠ ไม่พบปุ่ม RUN (btn-lilac) — ข้ามการ refresh")
    except Exception as e:
        log(f"    ⚠ RUN refresh: {e}")

    # ── ติ๊ก Select All (Step 3) ──
    log(f"  → ติ๊ก Select All (Step 3)")
    order_count_s3 = 0
    try:
        order_count_s3 = await js_tick_select_all(page)
        log(f"    {'✓ Select All เรียบร้อย' if order_count_s3 else '⚠ ไม่พบ checkbox — ลอง Step 3 ต่อไป'}")
        await page.wait_for_timeout(200)
    except Exception as e:
        log(f"    ⚠ Select All: {e}")

    # ── Step 3: FULL TAX ──
    log(f"  → Step 3: Full Tax")
    try:
        prepare_complete_event(signal)
        if not await js_click_button(page, "FULL TAX"):
            log(f"  ❌ ไม่พบปุ่ม Step 3 (FULL TAX)")
            await _screenshot(page, f"error_shopee{shop_id}_step3_notfound")
            return False

        await page.wait_for_timeout(1000)
        await wait_for_complete_popup(page, shop_id, signal, timeout=calc_timeout(order_count_s3))
        log(f"  ✅ Step 3 OK")

    except Exception as e:
        log(f"  ❌ Step 3 ล้มเหลว: {e}")
        await _screenshot(page, f"error_shopee{shop_id}_step3")
        return False

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
        log(f"  ❌ โหลดหน้า timeout: {url}")
        return False

    if sync_date:
        log(f"  → เซ็ตวันที่: {sync_date}")
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ ไม่พบ date field — ใช้วันที่ default")

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
        log(f"  ❌ Step 1 ล้มเหลว: {e}")
        await _screenshot(page, f"error_tiktok{shop_id}_step1")
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
        log(f"  ❌ โหลดหน้า timeout: {url}")
        return False

    if sync_date:
        log(f"  → เซ็ตวันที่: {sync_date}")
        if not await set_date_field(page, sync_date):
            log(f"    ⚠ ไม่พบ date field — ใช้วันที่ default")

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
        log(f"  ❌ Step 1 ล้มเหลว: {e}")
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
            log(f"  ❌ ไม่พบปุ่ม SYNC DETAIL (sync_detail)")
            await _screenshot(page, f"error_lazada{shop_id}_step3_notfound")
            return False

        log(f"    คลิก: {result}")
        await wait_for_modal_and_confirm(page, name)
        await wait_for_operation(page)
        log(f"  ✅ Step 3 OK")

    except Exception as e:
        log(f"  ❌ Step 3 ล้มเหลว: {e}")
        await _screenshot(page, f"error_lazada{shop_id}_step3")
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
                   sync_date: str = None, start_date: str = None, end_date: str = None):
    """
    เปิด browser ครั้งเดียว วนรันทุก shop ทุกวันในช่วงที่กำหนด
    target_id  : รัน shop เดียว (api_id)
    platform   : รันทุก shop ของ platform นั้น
    visible    : True = เห็น browser / False = headless
    sync_date  : วันเดียว (YYYY-MM-DD) — ถ้าไม่ระบุใช้วันนี้
    start_date / end_date : ช่วงวัน (เปิด browser ครั้งเดียว)
    """
    if not SESSION_FILE.exists():
        log("❌ ยังไม่มี session กรุณารัน: python trcloud_sync_browser.py --setup")
        return

    # ── กำหนดช่วงวันที่ ──
    if start_date and end_date:
        try:
            d_start = date.fromisoformat(start_date)
            d_end   = date.fromisoformat(end_date)
        except ValueError as e:
            log(f"❌ วันที่ไม่ถูกต้อง: {e}")
            return
        if d_start > d_end:
            log("❌ start-date ต้องน้อยกว่าหรือเท่ากับ end-date")
            return
    elif sync_date:
        try:
            d_start = d_end = date.fromisoformat(sync_date)
        except ValueError as e:
            log(f"❌ วันที่ไม่ถูกต้อง: {e}")
            return
    else:
        d_start = d_end = date.today()

    total_days = (d_end - d_start).days + 1

    log_path = init_log()

    # ── เลือก shops ──
    if target_id is not None:
        shops = [s for s in SHOPS if s["api_id"] == target_id]
        if not shops:
            log(f"❌ ไม่พบ shop id={target_id}")
            close_log()
            return
    elif platform is not None:
        shops = [s for s in SHOPS if s["platform"] == platform.lower()]
        if not shops:
            log(f"❌ ไม่พบ shop ของ platform={platform}")
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

            log("ตรวจสอบ session...")
            await page.goto(f"{APP_URL}/", wait_until="networkidle", timeout=30000)
            if "login" in page.url.lower():
                log("❌ Session หมดอายุ กรุณารัน --setup ใหม่")
                await browser.close()
                return
            log("✅ Session ใช้ได้")

            log(f"\n{'='*55}")
            log(f"TRCloud Browser Sync — {len(shops)} shop(s) × {total_days} day(s)")
            if total_days > 1:
                log(f"ช่วงวันที่: {d_start} → {d_end}")
            log(f"{'='*55}")

            job_i   = 0
            current = d_start
            while current <= d_end:
                if total_days > 1:
                    log(f"\n{'─'*55}")
                    log(f"วันที่: {current}")
                    log(f"{'─'*55}")

                for shop in shops:
                    job_i += 1
                    log(f"\n[{job_i}/{total}] {shop['name']} ({shop['platform'].upper()})")
                    fn = SYNC_FN.get(shop["platform"])
                    if fn is None:
                        log(f"  ⚠ ไม่รองรับ platform: {shop['platform']}")
                        continue

                    ok = await fn(page, shop, sync_date=str(current), signal=signal)
                    if ok:
                        success += 1
                    else:
                        label = f"{shop['name']}@{current}" if total_days > 1 else shop["name"]
                        failed.append(label)

                current += timedelta(days=1)

            log(f"\n{'='*55}")
            log(f"สรุป: ✅ {success}/{total} สำเร็จ")
            if failed:
                log(f"      ❌ ล้มเหลว: {', '.join(failed)}")
            log(f"{'='*55}")
            log(f"Log บันทึกที่: logs\\{log_path.name}")

            ts_done = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if failed:
                notify_gmail(
                    f"[TRCloud ORDER] ❌ มี {len(failed)} รายการล้มเหลว ({ts_done})",
                    f"สรุป ORDER sync: {success}/{total} สำเร็จ\n\nล้มเหลว:\n" + "\n".join(f"  - {f}" for f in failed) + f"\n\nLog: logs\\{log_path.name}",
                )
            else:
                notify_gmail(
                    f"[TRCloud ORDER] ✅ {success}/{total} สำเร็จ ({ts_done})",
                    f"สรุป ORDER sync: {success}/{total} สำเร็จทั้งหมด\n\nLog: logs\\{log_path.name}",
                )

            await browser.close()
    finally:
        close_log()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="TRCloud Browser Sync (Playwright)")
    parser.add_argument("--setup",      action="store_true",  help="Login และ save session (รันครั้งแรก)")
    parser.add_argument("--rv",         action="store_true",  help="Sync RECEIPT [RV] (เฉพาะ Step 1)")
    parser.add_argument("--shop",       type=int,             help="Sync เฉพาะ shop id นี้")
    parser.add_argument("--platform",   choices=["shopee", "tiktok", "lazada"], help="Sync ทุก shop ของ platform")
    parser.add_argument("--visible",    action="store_true",  help="แสดง browser ขณะรัน (debug mode)")
    parser.add_argument("--date",       type=str, default=None, help="วันที่ที่ต้องการ sync เช่น 2026-03-11 (default: วันนี้)")
    parser.add_argument("--start-date", type=str, default=None, dest="start_date", help="วันเริ่มต้น (ใช้คู่กับ --end-date)")
    parser.add_argument("--end-date",   type=str, default=None, dest="end_date",   help="วันสิ้นสุด (ใช้คู่กับ --start-date)")
    args = parser.parse_args()

    if args.setup:
        asyncio.run(setup_session())

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
        ))

    else:
        asyncio.run(run_sync(
            target_id=args.shop,
            platform=args.platform,
            visible=args.visible,
            sync_date=args.date,
            start_date=args.start_date,
            end_date=args.end_date,
        ))


if __name__ == "__main__":
    main()
