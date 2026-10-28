"""
Ticketbox helper – script tự chạy toàn bộ các bước mua vé, chỉ dừng lại ở những chỗ cần người thật.

Script TỰ làm:
  1. Mở Chrome với profile riêng (giữ đăng nhập giữa các lần chạy).
  2. Tự đếm ngược tới giờ mở bán.
  3. Tự tải lại trang sự kiện cho tới khi nút "Mua vé" bấm được, rồi tự bấm.
  4. Tự nhận diện trang hiện tại (theo bất kỳ thứ tự nào):
       - Trang nhập mã early bird  -> tự điền --code và xác nhận.
       - CAPTCHA                   -> kêu bíp, chờ BẠN giải xong (script tự đi tiếp, không cần bấm Enter).
       - Sơ đồ chọn khu vực         -> tự bấm zone theo --zone (ưu tiên theo thứ tự), chỉnh số lượng
                                      trong pop-up, bấm "Tiếp tục". Hết vé thì thử zone kế tiếp, lặp lại.
  5. Dừng ở bước thanh toán, kêu bíp để BẠN kiểm tra và thanh toán.

Cấu hình riêng từng ngày (tài khoản, ngày, mã, zone, số lượng) nằm trong run_day1.sh / run_day2.sh.
Mỗi lần chạy = 1 cửa sổ Chrome = 1 tài khoản (--profile).

Script KHÔNG làm (có chủ ý): giải/vượt CAPTCHA, nhập mật khẩu, nhập thông tin thanh toán, tạo tài khoản.

Giao diện Ticketbox có thể thay đổi; nếu không nhận được trang/nút, chỉnh các hằng TEXT_* / SEL_* bên dưới.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import signal
import sys
import time
import unicodedata

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

# ============ CẤU HÌNH CHUNG cho mọi tài khoản / ngày ============
EVENT_URL = "https://ticketbox.vn/the-aura-khong-the-thay-the-isaac-jun-pham-will-st-son-thach-26624"
OPEN_AT = ""   # giờ mở bán theo giờ máy ví dụ "2026-11-15 10:00:00" để "" nếu đang mở bán rồi
# ==================================================================


# Nhãn trên Ticketbox (tiếng Việt / tiếng Anh). Chỉnh nếu site đổi chữ.
TEXT_BUY = re.compile(r"(mua vé|buy ticket|book now|đặt vé)", re.I)
TEXT_CONTINUE = re.compile(r"(tiếp tục|continue|thanh toán|checkout)", re.I)
TEXT_SUBMIT_CODE = re.compile(r"(xác nhận|áp dụng|gửi|submit|apply|confirm|tiếp tục|continue)", re.I)
TEXT_CODE_PAGE = re.compile(r"(nhập mã|mã presale|mua vé sớm|presale|early ?bird|code)", re.I)
TEXT_CODE_ERROR = re.compile(r"(không hợp lệ|sai mã|invalid|incorrect|hết hạn|expired)", re.I)
# Hộp thoại còn đơn cũ chưa thanh toán của cùng sự kiện -> luôn tự bấm "Hủy đơn, Mua vé mới"
TEXT_OLD_ORDER = re.compile(r"đơn hàng chưa hoàn (thành|tất)", re.I)
TEXT_CANCEL_OLD = re.compile(r"h(ủ|uỷ|ũy|uy)\s*đơn|mua vé mới", re.I)
# CAPTCHA của Ticketbox nằm ngay trong trang: "Xác Minh Người Dùng – Chống bot tự động mua vé – Kéo mũi tên qua phải..."
TEXT_CAPTCHA = re.compile(r"(xác minh người dùng|chống bot|kéo mũi tên)", re.I)

# Khung CAPTCHA của bên thứ ba (khi bắt giải). Biểu tượng reCAPTCHA nhỏ ở góc màn hình (~256x60) chạy ngầm,
# không phải câu đố -> chỉ tính khung đủ lớn (xem CAPTCHA_MIN_HEIGHT).
SEL_CAPTCHA = (
    "iframe[src*='captcha'], iframe[src*='recaptcha'], iframe[src*='hcaptcha'], "
    "iframe[src*='turnstile'], iframe[title*='challenge' i], .g-recaptcha, .h-captcha, .cf-turnstile"
)
SEL_CODE_INPUT = (
    "input[placeholder*='mã' i], input[placeholder*='code' i], "
    "input[name*='code' i], input[id*='code' i]"
)

# Khoảng nghỉ giữa các lần tải lại trang sự kiện (giây). Đừng giảm quá thấp: dễ bị chặn.
REFRESH_INTERVAL = 4.0
# Thời gian tối đa chờ qua các bước early bird / CAPTCHA để tới trang chọn vé (giây).
# Bao gồm cả thời gian ngồi hàng chờ (queue) sau CAPTCHA, có thể rất lâu.
GATE_TIMEOUT = 3 * 3600
# Thời gian tối đa script tự thử các zone trên sơ đồ / canh vé nhả trước khi giao lại cho bạn (giây).
# Gõ "huy" + Enter trong terminal để dừng canh sớm và tự chọn zone.
ZONE_RETRY_TIMEOUT = 20 * 60
# Thời gian tối đa chờ nút "Tiếp tục" trong pop-up hết khoá sau khi chỉnh số lượng (giây); quá thì giao cho bạn bấm.
CONTINUE_WAIT = 15


# ---------- Ctrl+C an toàn ----------
# Ctrl+C đúng lúc đang chờ Chrome trả lời làm đứt kết nối với Chrome -> không đóng Chrome được, mất phiên đăng nhập.
# Nên chỉ dừng ở chỗ an toàn (lúc đang nghỉ / chờ bạn bấm Enter); bấm lúc khác thì dừng ngay sau thao tác đang làm.
_stop_requested = False
_safe_to_stop = False


def _on_sigint(signum, frame):
    global _stop_requested
    if _stop_requested and not _safe_to_stop:
        print("\nCtrl+C lần 2 – thoát ngay (có thể phải đăng nhập lại bằng login.sh).")
        os._exit(1)
    _stop_requested = True
    if _safe_to_stop:
        raise KeyboardInterrupt
    print("\nCtrl+C – sẽ dừng ngay sau thao tác hiện tại...")


def nap(seconds: float) -> None:
    """time.sleep có thể ngắt an toàn bằng Ctrl+C."""
    global _safe_to_stop
    if _stop_requested:
        raise KeyboardInterrupt
    _safe_to_stop = True
    try:
        time.sleep(seconds)
    finally:
        _safe_to_stop = False


def ask(prompt: str) -> str:
    """input() có thể ngắt an toàn bằng Ctrl+C."""
    global _safe_to_stop
    if _stop_requested:
        raise KeyboardInterrupt
    try:
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass
    _safe_to_stop = True
    try:
        return input(prompt)
    finally:
        _safe_to_stop = False


def confirm_close(what: str) -> None:
    """Chỉ đóng Chrome khi bạn gõ 'xong' – lỡ tay bấm Enter lúc đang thanh toán thì không bị đóng."""
    while ask(f"{what} thì gõ 'xong' rồi Enter để đóng Chrome: ").strip().lower() != "xong":
        print("  (Chrome vẫn mở. Gõ đúng chữ 'xong' để đóng.)")


def beep(times: int = 3) -> None:
    for _ in range(times):
        sys.stdout.write("\a")
        sys.stdout.flush()
        time.sleep(0.3)


def pause_for_user(msg: str) -> None:
    beep()
    ask(f"\n>>> {msg}\n    Xong thì bấm Enter để script chạy tiếp... ")


def wait_until(open_at: dt.datetime | None) -> None:
    if not open_at:
        return
    while True:
        remaining = (open_at - dt.datetime.now()).total_seconds()
        if remaining <= 0:
            print()
            return
        print(f"\rChờ mở bán: còn {int(remaining)} giây   ", end="", flush=True)
        nap(min(remaining, 1))


def ensure_logged_in(page: Page) -> None:
    page.goto("https://ticketbox.vn/", wait_until="domcontentloaded")
    # Đã đăng nhập thì thanh trên cùng hiện "Tài khoản" thay cho "Đăng nhập | Đăng ký".
    try:
        page.get_by_text("Tài khoản", exact=True).first.wait_for(state="visible", timeout=8000)
        print("Đã đăng nhập.")
    except PWTimeout:
        pause_for_user("Bạn chưa đăng nhập. Đăng nhập bằng Google thì Ctrl+C, chạy ./login.sh <profile> rồi chạy lại; "
                       "đăng nhập bằng email/mật khẩu thì đăng nhập ngay trong cửa sổ Chrome này.")


def buy_button(page: Page, showtimes: list[str]):
    """Nút "Mua vé ngay" của ngày diễn ưu tiên nhất còn bấm được, kèm tên ngày đó.

    Mục "Lịch diễn" gồm các dòng `.ant-collapse-header`, mỗi dòng có ngày giờ + nút riêng
    ("Mua vé ngay" hoặc "Hết vé"). Nút "Mua vé ngay" ở banner trên cùng chỉ cuộn xuống mục này,
    nên chỉ lấy nút trong từng dòng.
    """
    rows = page.locator(".ant-collapse-header")
    for showtime in showtimes or [""]:
        row = rows.filter(has_text=showtime) if showtime else rows
        btn = row.get_by_role("button", name=TEXT_BUY).first
        if _visible(btn) and btn.is_enabled():
            return btn, showtime or row.first.inner_text(timeout=1000).split("\n")[0]
    return None, None


def wait_for_buy_button(page: Page, event_url: str, showtimes: list[str]) -> None:
    attempt = 0
    while True:
        attempt += 1
        page.goto(event_url, wait_until="domcontentloaded")
        try:
            page.locator(".ant-collapse-header").first.wait_for(state="visible", timeout=5000)
            btn, picked = buy_button(page, showtimes)
            if btn:
                print(f"\nNgày {picked} đã mở bán (lần thử {attempt}), bấm!")
                btn.scroll_into_view_if_needed()
                btn.click()
                return
        except PWTimeout:
            pass
        print(f"\rChưa mở bán ngày cần mua, thử lại sau {REFRESH_INTERVAL}s (lần {attempt})   ", end="", flush=True)
        nap(REFRESH_INTERVAL)


# ---------- Nhận diện trang hiện tại ----------


def _visible(locator) -> bool:
    try:
        return locator.count() > 0 and locator.first.is_visible()
    except Exception:
        return False


def is_seat_map(page: Page) -> bool:
    # Trang sơ đồ: tiêu đề "Chọn khu vực" + "Bấm vào khu vực để chọn vé". CAPTCHA đè lên cùng URL nên loại trừ.
    return _visible(page.get_by_text("Chọn khu vực", exact=True)) and not is_captcha(page)


def is_ticket_page(page: Page) -> bool:
    return is_seat_map(page)


def is_login_modal(page: Page) -> bool:
    # Chưa đăng nhập (hoặc hết phiên) thì bấm "Mua vé ngay" sẽ hiện hộp "Đăng nhập" có ô mật khẩu.
    return _visible(page.locator("input[type='password']"))


CAPTCHA_MIN_HEIGHT = 120


def _on_top(locator, limit: int = 5, min_height: int = 2) -> bool:
    """Có phần tử nào thật sự nhìn thấy trên màn hình không: có kích thước, không trong suốt,
    và không bị thứ khác đè lên. (Ticketbox giải CAPTCHA xong chỉ ẩn nó đi, chữ vẫn còn trong trang.)"""
    try:
        n = min(locator.count(), limit)
    except Exception:
        return False
    for i in range(n):
        try:
            if locator.nth(i).evaluate("""(e, minH) => {
                const r = e.getBoundingClientRect();
                if (r.width < 2 || r.height < minH) return false;
                for (let a = e; a && a.nodeType === 1; a = a.parentElement) {
                    const st = getComputedStyle(a);
                    if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity) < 0.1) return false;
                }
                const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
                const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
                const top = document.elementFromPoint(x, y);
                return !!top && (top === e || e.contains(top) || top.contains(e));
            }""", min_height, timeout=500):
                return True
        except Exception:
            continue
    return False


def is_captcha(page: Page) -> bool:
    return _on_top(page.locator(SEL_CAPTCHA), min_height=CAPTCHA_MIN_HEIGHT) or _on_top(page.get_by_text(TEXT_CAPTCHA))


def is_code_page(page: Page) -> bool:
    if not _visible(page.locator(SEL_CODE_INPUT)):
        return False
    try:
        return bool(TEXT_CODE_PAGE.search(page.inner_text("body", timeout=1000)))
    except PWTimeout:
        return False


# ---------- Xử lý từng loại trang ----------


def handle_code_page(page: Page, code: str, tried: set[str]) -> None:
    """Trang mã presale / early bird: web "MUA VÉ SỚM ĐANG DIỄN RA" + nút "Xác nhận", điện thoại "Presale đang diễn ra"
    + nút "Tiếp tục". Ô "Nhập mã tại đây"; nút khoá tới khi có mã."""
    if not code or page.url in tried:
        beep()
        print("\n>>> " + ("Trang yêu cầu mã presale nhưng CODE trong run_dayX.sh đang trống." if not code
                          else "Đã nhập mã mà vẫn ở trang mã (mã sai / hết lượt?).")
              + " Hãy tự nhập mã và bấm tiếp – script chờ.")
        while is_code_page(page):
            nap(0.5)
        return
    tried.add(page.url)
    print("Trang nhập mã presale – đang điền mã...")
    field = page.locator(SEL_CODE_INPUT).first
    field.fill(code)
    # Nút ngay sau ô nhập (tránh bấm nhầm nút khác trên trang); chờ hết khoá.
    submit = field.locator("xpath=following::button[1]")
    if not (_visible(submit) and TEXT_SUBMIT_CODE.search(submit.inner_text(timeout=1000) or "")):
        submit = page_button(page, TEXT_SUBMIT_CODE)
    deadline = time.time() + 3
    while time.time() < deadline and not (_visible(submit) and submit.is_enabled()):
        nap(0.1)
    if _visible(submit) and submit.is_enabled():
        submit.click(timeout=3000, no_wait_after=True)
    else:
        field.press("Enter")
    deadline = time.time() + 5         # chờ trang mã biến mất; còn ở lại + báo lỗi thì lượt sau sẽ nhờ bạn
    while time.time() < deadline and is_code_page(page):
        nap(0.2)
    if is_code_page(page):
        try:
            err = TEXT_CODE_ERROR.search(page.inner_text("body", timeout=1000))
        except PWTimeout:
            err = None
        print("  Mã bị báo lỗi." if err else "  Vẫn ở trang mã sau khi bấm.")


def wait_for_captcha_solved(page: Page, profile: str = "") -> None:
    dump_page(page, "captcha", profile)
    print("\n>>> Có CAPTCHA (xoay/kéo đầu chó vàng) – hãy giải bình tĩnh, chuẩn hơn là nhanh. Script tự chạy tiếp khi xong.")
    beep()
    while is_captcha(page):
        nap(0.5)
    print("CAPTCHA đã xong, script chạy tiếp. (Nếu vào hàng chờ, cứ để yên.)")


def pass_gates_until_ticket_page(page: Page, code: str, profile: str = "") -> bool:
    """Vượt qua trang mã early bird và CAPTCHA (theo bất kỳ thứ tự nào) cho tới trang chọn vé."""
    tried_code: set[str] = set()
    deadline = time.time() + GATE_TIMEOUT
    while time.time() < deadline:
        if is_ticket_page(page):
            return True
        if is_login_modal(page):
            pause_for_user("Ticketbox đòi đăng nhập. Hãy tự đăng nhập (kể cả ô xác minh), rồi tự bấm lại 'Mua vé ngay' nếu cần.")
        elif is_captcha(page):
            wait_for_captcha_solved(page, profile)
        elif is_code_page(page):
            handle_code_page(page, code, tried_code)
        nap(0.3)
    return False


def wait_until_left_ticket_page(page: Page, msg: str, quantity: int = 0) -> None:
    """Giao cho người dùng chọn zone; bấm zone xong thì script tự chọn số lượng + Tiếp tục.
    Tự phát hiện khi trang đã sang bước thanh toán."""
    beep()
    print(f"\n>>> {msg}\n    Script tự đi tiếp khi trang chuyển sang thanh toán (không cần bấm Enter).")
    while not left_ticket_page(page):
        try:
            if quantity and is_seat_map(page) and handle_user_popup(page, quantity):
                return
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"Lỗi {type(e).__name__} khi xử lý pop-up – tiếp tục chờ bạn.")
        nap(0.5)


# ---------- Sơ đồ chọn khu vực ----------


def zone_popup(page: Page):
    # Pop-up sau khi bấm zone: "Khu ĐỈNH NÓC", nút - / số lượng / +, "Chọn khu vực khác", "Tiếp tục - 3.500.000 đ".
    return page.locator("[role='dialog'], .ant-modal").filter(has_text=re.compile(r"chọn khu vực khác", re.I)).last


def close_zone_popup(page: Page, popup) -> None:
    try:
        other = popup.get_by_text(re.compile(r"chọn khu vực khác", re.I))
        if _visible(other):
            other.first.click(timeout=2000)
        else:
            page.keyboard.press("Escape")
    except Exception:
        pass   # bị CAPTCHA che... thì thôi, không cố
    nap(0.2)


def set_quantity(popup, quantity: int) -> int:
    qty_input = popup.locator("input").first
    # Nút "-" ngay trước ô số lượng, "+" ngay sau (nút có thể chỉ là icon, không có chữ).
    plus = qty_input.locator("xpath=following::button[1]")
    minus = qty_input.locator("xpath=preceding::button[1]")

    def current() -> int:
        try:
            return int(qty_input.input_value(timeout=1000) or 0)
        except Exception:
            return 0

    for _ in range(20):
        n = current()
        if n == quantity:
            break
        btn = plus if n < quantity else minus
        if not _visible(btn) or not btn.first.is_enabled():
            break  # đạt giới hạn còn lại của zone / mỗi đơn
        btn.first.click()
        nap(0.1)
    return current()


def _norm(text: str) -> str:
    # "Trôi Theo Con Nước (R2)", "TRÔI THEO CON NƯỚC R2", "TRÔI_THEO_CON_NƯỚC_R2" -> "troitheoconnuocr2".
    # Bỏ cả dấu tiếng Việt: "Hoả"/"Hỏa"/"Hoa" và chữ có dấu gõ bằng bộ gõ khác nhau đều khớp nhau.
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").replace("đ", "d").replace("Đ", "D")
    return re.sub(r"[\s_()\-]+", "", text).casefold()


# Sơ đồ Ticketbox vẽ bằng Konva lên <canvas>: chữ zone không có trong HTML, phải hỏi Konva.
_KONVA_STRINGS_JS = """
    const strs = (v, d) => {
        if (typeof v === 'string') return [v];
        if (d > 2 || !v || typeof v !== 'object') return [];
        if (Array.isArray(v)) return v.slice(0, 20).flatMap(x => strs(x, d + 1));
        return Object.keys(v).slice(0, 40).flatMap(k => strs(v[k], d + 1));
    };
    const nodeStrings = n => strs(n.attrs, 0).concat(n.getClassName() === 'Text' ? [n.text()] : []);
"""

# Trả về các điểm nên bấm cho zone khớp tên. Tên zone có thể nằm ở chữ (Text), name/id, hoặc thuộc tính
# riêng mà trang gắn vào hình (vd "TRÔI_THEO_CON_NƯỚC_R2"), nên dò mọi chuỗi trong attrs.
_ZONE_POINTS_JS = """(target) => {
    const norm = t => (t || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/[đĐ]/g, 'd')
                                  .replace(/[\\s_()\\-]+/g, '').toLowerCase();
""" + _KONVA_STRINGS_JS + """
    const pts = [];
    const stages = (window.Konva && window.Konva.stages) || [];
    for (const st of stages) {
        const box = st.container().getBoundingClientRect();
        const at = r => [box.left + r.x + r.width / 2, box.top + r.y + r.height / 2];
        for (const n of st.find(() => true)) {
            if (!n.isVisible() || !nodeStrings(n).some(c => norm(c) === target || (norm(c).includes(target) && target.length > 3))) continue;
            const r = n.getClientRect();
            pts.push(at(r), [box.left + r.x + 6, box.top + r.y + 6]);
            const p = n.getParent();
            if (p && p.getType && p.getType() !== 'Layer') {
                const pr = p.getClientRect();
                pts.push(at(pr), [box.left + pr.x + 6, box.top + pr.y + 6]);
            }
        }
    }
    if (stages.length) return pts;
    // Không có Konva: sơ đồ là HTML/SVG thường
    const hits = [...document.querySelectorAll('body *')].filter(e => {
        if (e.closest("[role='dialog'], .ant-modal")) return false;
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && norm(e.textContent) === target;
    });
    hits.filter(e => !hits.some(o => o !== e && e.contains(o))).forEach(e => {
        const r = e.getBoundingClientRect(); pts.push([r.x + r.width / 2, r.y + r.height / 2]);
    });
    return pts;
}"""

_MAP_NAMES_JS = """() => {
""" + _KONVA_STRINGS_JS + """
    const out = {konva: !!window.Konva, stages: 0, nodes: 0, names: []};
    for (const st of (window.Konva && window.Konva.stages) || []) {
        out.stages++;
        for (const n of st.find(() => true)) {
            out.nodes++;
            for (const t of nodeStrings(n)) {
                const v = t.replace(/\\s+/g, ' ').trim();
                if (/[A-Za-zÀ-ỹ]/.test(v) && v.length < 40 && !/^(#|rgb|source-|butt|round|miter|left|center|right|top|middle|bottom|normal|bold)/i.test(v))
                    out.names.push(v);
            }
        }
    }
    out.names = [...new Set(out.names)];
    return out;
}"""

# Toàn bộ cấu trúc sơ đồ Konva (loại hình, thuộc tính, vị trí) để chỉnh script khi không tìm được zone.
_KONVA_DUMP_JS = """() => {
    const out = [];
    for (const st of (window.Konva && window.Konva.stages) || []) {
        for (const n of st.find(() => true)) {
            const a = {};
            for (const [k, v] of Object.entries(n.attrs || {})) {
                if (['string', 'number', 'boolean'].includes(typeof v)) a[k] = typeof v === 'string' ? v.slice(0, 100) : v;
                else if (v && typeof v === 'object') { try { a[k] = JSON.stringify(v).slice(0, 300); } catch (e) { a[k] = '[object]'; } }
            }
            const r = n.getClientRect();
            out.push({cls: n.getClassName(), parent: n.getParent() && n.getParent().getClassName(), attrs: a,
                      rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]});
            if (out.length >= 600) return out;
        }
    }
    return out;
}"""


def map_zone_names(page: Page) -> dict:
    try:
        return page.evaluate(_MAP_NAMES_JS)
    except Exception as e:
        return {"error": str(e)}


# Sơ đồ thật: mỗi zone là một Group Konva chỉ có mã số "data-section-id"; chữ trên sơ đồ vẽ thành hình (Path),
# không đọc được. Tên zone nằm trong dữ liệu trang tải về từ máy chủ Ticketbox -> ghi lại các phản hồi JSON
# rồi tìm object nào chứa mã zone, lấy các chuỗi trong object đó làm tên zone.
_json_responses: list = []


def record_json_responses(ctx) -> None:
    def on_response(r):
        if "json" in (r.headers.get("content-type") or "") and len(_json_responses) < 300:
            _json_responses.append(r)
    ctx.on("response", on_response)


_SECTION_IDS_JS = """() => [].concat(...((window.Konva && window.Konva.stages) || []).map(st =>
    st.find('Group').map(g => g.getAttr('data-section-id')).filter(x => x != null)))"""

# Điểm bấm cho từng zone: điểm gần tâm nhất mà Konva xác nhận đúng là hình của zone đó
# (tránh bấm trúng zone nhỏ lồng bên trong, vd "TRÔI THEO CON NƯỚC L2" nằm trong "VỀ MIỀN TÂY L1").
_SECTION_POINTS_JS = """(ids) => {
    const out = {};
    for (const st of (window.Konva && window.Konva.stages) || []) {
        const box = st.container().getBoundingClientRect();
        for (const g of st.find('Group')) {
            const sid = g.getAttr('data-section-id');
            if (sid == null || !ids.includes(sid)) continue;
            const r = g.getClientRect(), cx = r.x + r.width / 2, cy = r.y + r.height / 2;
            const cand = [];
            for (let i = 1; i < 10; i++) for (let j = 1; j < 10; j++) cand.push([r.x + r.width * i / 10, r.y + r.height * j / 10]);
            cand.sort((a, b) => Math.hypot(a[0] - cx, a[1] - cy) - Math.hypot(b[0] - cx, b[1] - cy));
            for (const [x, y] of cand) {
                const hit = st.getIntersection({x, y});
                if (hit && (hit === g || hit.findAncestors('Group').includes(g))) { out[sid] = [box.left + x, box.top + y]; break; }
            }
        }
    }
    return out;
}"""


def _strings(o, depth=0) -> list:
    """Chuỗi trong object và các mục con gần (vd tên hạng vé "Bà Năm (left)" trong section.ticketType.name)."""
    if isinstance(o, str):
        return [o]
    if depth >= 2:
        return []
    if isinstance(o, dict):
        return [x for v in o.values() for x in _strings(v, depth + 1)]
    if isinstance(o, list):
        return [x for v in o[:10] for x in _strings(v, depth + 1)]
    return []


def section_names(page: Page) -> dict:
    """{mã zone: [các tên tìm được]} từ dữ liệu JSON trang đã tải."""
    try:
        ids = set(page.evaluate(_SECTION_IDS_JS))
    except Exception:
        return {}
    ids |= {str(i) for i in ids}
    found: dict = {}

    def walk(o, depth=0):
        if depth > 10:
            return
        if isinstance(o, dict):
            hits = [v for v in o.values() if isinstance(v, (int, str)) and not isinstance(v, bool) and v in ids]
            if hits:
                strs = [v for v in _strings(o) if 1 < len(v) < 80 and v not in ids]
                for sid in hits:
                    found.setdefault(int(sid), set()).update(strs)
            for v in o.values():
                walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o:
                walk(v, depth + 1)

    for r in list(_json_responses):
        try:
            walk(r.json())
        except Exception:
            continue
    return {k: sorted(v) for k, v in found.items()}


def _zone_label(strings: list) -> str:
    """Tên dễ đọc nhất trong các chuỗi của một zone (bỏ mã màu, ngày giờ, trạng thái), kèm trạng thái nếu có."""
    status = next((x for x in strings if x in ("sold_out", "book_now")), "")
    names = [x for x in strings if not re.match(r"^(#|\d{4}-\d\d-\d\d|[a-z_]+$|Sold out$|Book now$)", x) and len(x) <= 40]
    best = next((x for x in names if "(" in x), names[0] if names else "?")   # ưu tiên tên dạng "Trôi Theo Con Nước (R2)"
    return best + (" [hết]" if status == "sold_out" else "")


def match_sections(names: dict, zone: str) -> list:
    """Mã các zone khớp tên: khớp chính xác trước, không có thì tên trên trang "chứa" tên bạn ghi."""
    target = _norm(zone)
    exact = [sid for sid, ns in names.items() if any(_norm(n) == target for n in ns)]
    if exact:
        return exact
    return [sid for sid, ns in names.items() if any(target in _norm(n) for n in ns)]


# Thời gian chờ pop-up sau khi bấm zone (ms): zone dữ liệu báo còn vé chờ lâu hơn, zone hết vé / không rõ chờ ngắn.
POPUP_WAIT_OPEN = 2500
POPUP_WAIT_SOLDOUT = 800


def zone_states(names: dict, zones: list[str]) -> dict:
    """Trạng thái từng zone trong ZONES theo dữ liệu Ticketbox: "open" (còn vé), "soldout" hoặc "unknown"."""
    out = {}
    for zone in zones:
        sids = match_sections(names, zone)
        if not sids:
            out[zone] = "unknown"
            continue
        sold = [any(x == "sold_out" or x.lower() == "sold out" for x in names[sid]) for sid in sids]
        out[zone] = "soldout" if all(sold) else "open"
    return out


def click_zone(page: Page, zone: str, names: dict | None = None, wait_ms: int = POPUP_WAIT_OPEN):
    """Bấm vào zone trên sơ đồ. Trả về (pop-up hoặc None, số điểm tìm được cho zone này)."""
    points = []
    sids = match_sections(names or {}, zone)
    if sids:
        try:
            points += list(page.evaluate(_SECTION_POINTS_JS, sids).values())
        except Exception:
            pass
    try:
        points += page.evaluate(_ZONE_POINTS_JS, _norm(zone))
    except Exception:
        pass
    popup = zone_popup(page)
    for x, y in points:
        try:
            page.mouse.click(x, y)
            popup.wait_for(state="visible", timeout=wait_ms)
            return popup, len(points)
        except PWTimeout:
            continue
    return None, len(points)


# Nút "Tiếp tục" trong pop-up chọn zone đã bấm được chưa (chạy trong trang, Chrome kiểm tra mỗi khung hình).
_CONTINUE_READY_JS = """() => {
    const dlg = [...document.querySelectorAll("[role='dialog'], .ant-modal")].filter(d => /chọn khu vực khác/i.test(d.innerText)).pop();
    if (!dlg) return false;
    return [...dlg.querySelectorAll('button')].some(b => /tiếp tục|continue/i.test(b.innerText) && !b.disabled && b.offsetParent);
}"""


def continue_button(popup):
    # Nút cuối pop-up: "Vui lòng chọn vé - 2.800.000 đ" (khoá) -> "Tiếp tục - 2.800.000 đ" (bấm được).
    return popup.locator("button").filter(has_text=re.compile(r"tiếp tục|vui lòng chọn vé|continue", re.I)).last


def _ready(btn) -> bool:
    try:
        return btn.count() > 0 and btn.is_visible() and btn.is_enabled(timeout=1000) and bool(TEXT_CONTINUE.search(btn.inner_text(timeout=1000)))
    except Exception:
        return False


def left_ticket_page(page: Page) -> bool:
    # Đã sang bước thanh toán: không còn CAPTCHA và đã rời trang chọn vé / sơ đồ.
    return not is_captcha(page) and ("select-ticket" not in page.url or not is_seat_map(page))


def wait_after_continue(page: Page, cont, seconds: float) -> str:
    """Sau khi bấm (hoặc chờ bạn bấm) Tiếp tục: CAPTCHA thì chờ bạn giải; nút sáng mà chưa đi thì bấm lại.
    Trả về "left" (sang thanh toán), "gone" (pop-up đóng, vẫn ở sơ đồ = vừa hết vé) hoặc "stuck"."""
    deadline = time.time() + seconds
    last_click = time.time()
    while time.time() < deadline:
        nap(0.25)
        if is_captcha(page):
            wait_for_captcha_solved(page)
            deadline = time.time() + max(seconds, 10)
            continue
        if left_ticket_page(page):
            return "left"
        if not _visible(zone_popup(page)):
            return "gone"
        if time.time() - last_click > 1.5 and _ready(cont):
            cont.click(timeout=3000, no_wait_after=True)
            last_click = time.time()
    return "stuck"


def other_dialog(page: Page):
    """Hộp thoại đang che sơ đồ mà không phải pop-up chọn zone hay CAPTCHA – vd còn đơn cũ chưa thanh toán của
    sự kiện này ("Huỷ đơn cũ"). Trả về hộp thoại (hoặc None)."""
    # Hộp thoại đơn cũ thật: "Đơn hàng chưa hoàn thành – Bạn đang có đơn hàng chưa hoàn tất. Bạn có muốn tiếp tục?
    # • 1 x CAT 3A – [Quay lại đơn cũ (12:33)] – Hủy đơn, Mua vé mới". Nhận theo chữ phòng khi không dùng khung hộp thoại chuẩn.
    old = page.get_by_text(TEXT_OLD_ORDER)
    if _on_top(old):
        return old.first.locator("xpath=ancestor::*[.//button or .//a][1]")
    dlg = page.locator(".ant-modal-wrap, [role='dialog'], .tbox-modal").filter(
        has_not_text=re.compile(r"chọn khu vực khác|xác minh người dùng", re.I))
    for k in range(min(dlg.count(), 5)):
        try:
            d = dlg.nth(k)
            if d.is_visible() and d.inner_text(timeout=1000).strip():
                return d
        except Exception:
            continue
    return None


def wait_other_dialog(page: Page) -> bool:
    """Hộp thoại đơn cũ chưa thanh toán -> tự bấm "Hủy đơn, Mua vé mới". Hộp thoại lạ khác -> không bấm gì,
    bíp, chờ bạn chọn. Trả về True nếu đã gặp hộp thoại."""
    d = other_dialog(page)
    if not d:
        return False
    try:
        text = " ".join(d.inner_text(timeout=1000).split())[:160]
    except Exception:
        text = ""
    if TEXT_OLD_ORDER.search(text):
        items = ", ".join(re.findall(r"\d+\s*x\s*[^•\n]+?(?=\s*(?:•|Quay lại|Hủy|Huỷ|$))", text)) or "?"
        cancel = d.get_by_text(TEXT_CANCEL_OLD)
        if _visible(cancel):
            print(f"\nCòn đơn cũ chưa thanh toán ({items}) -> tự bấm 'Hủy đơn, Mua vé mới'.")
            cancel.last.click(timeout=3000, no_wait_after=True)
            deadline = time.time() + 10
            while time.time() < deadline and other_dialog(page):
                nap(0.3)
            if not other_dialog(page):
                nap(0.5)
                return True
            # vẫn còn hộp thoại (vd hỏi xác nhận huỷ) -> giao bạn xử lý bên dưới
            try:
                text = " ".join((other_dialog(page) or d).inner_text(timeout=1000).split())[:160]
            except Exception:
                pass
    beep()
    if TEXT_OLD_ORDER.search(text):
        print(f"\n>>> Còn đơn cũ chưa thanh toán nhưng script chưa huỷ được: \"{text}\"\n"
              "    Hãy tự bấm 'Hủy đơn, Mua vé mới' – script chờ, hộp thoại đóng thì chạy tiếp.")
    else:
        print(f"\n>>> Có hộp thoại che sơ đồ: \"{text}\"\n    Hãy tự chọn. Script đứng yên chờ, hộp thoại đóng thì chạy tiếp.")
    while other_dialog(page):
        nap(0.5)
    nap(0.5)
    return True


def finish_popup(page: Page, popup, quantity: int, label: str) -> str:
    """Trong pop-up đang mở: chỉnh số lượng, bấm Tiếp tục.
    Trả về "left" (đã sang thanh toán), "soldout" (không chọn được vé) hoặc "gone"/"stuck"."""
    got = set_quantity(popup, quantity)
    if got == 0:
        print(f"{label}: không chọn được vé (hết vé?).")
        return "soldout"
    if got < quantity:
        print(f"{label}: chỉ chọn được {got}/{quantity} vé, vẫn đi tiếp.")
    cont = continue_button(popup)
    t0 = time.time()
    # Nút khoá ~1 giây trong lúc Ticketbox kiểm tra số vé. Để Chrome tự báo ngay khi nút hết khoá (theo từng khung hình)
    # thay vì hỏi đi hỏi lại – bấm được gần như tức thì.
    try:
        page.wait_for_function(_CONTINUE_READY_JS, timeout=CONTINUE_WAIT * 1000)
    except Exception:
        pass
    if _ready(cont):
        print(f"{label} x{got} → bấm Tiếp tục (nút sáng sau {time.time() - t0:.1f} giây)")
        cont.click(timeout=3000, no_wait_after=True)
        result = wait_after_continue(page, cont, 8)
    else:
        result = "stuck"
    if result == "stuck":
        # Không đóng pop-up (đóng là mất lượt): giao cho bạn bấm, script chờ tiếp + lo CAPTCHA.
        try:
            import pathlib
            pathlib.Path("debug").mkdir(exist_ok=True)
            pathlib.Path("debug", "popup.html").write_text(popup.evaluate("e => e.outerHTML", timeout=2000), encoding="utf-8")
        except Exception:
            pass
        beep()
        print(f"\n>>> {label}: đã chọn {got} vé nhưng nút Tiếp tục chưa bấm được. BẠN BẤM 'Tiếp tục' trong pop-up giúp – "
              "script giữ nguyên pop-up và tự lo phần sau (CAPTCHA thì bíp chờ bạn giải).")
        result = wait_after_continue(page, cont, 600)
    if result == "gone":
        print(f"{label}: pop-up đóng mà vẫn ở sơ đồ (có thể vừa hết vé).")
    return result


def handle_user_popup(page: Page, quantity: int) -> bool:
    """Bạn tự bấm zone (pop-up mở mà không phải do script) -> script chọn số lượng + Tiếp tục giúp bạn.
    Không chọn được thì để yên pop-up cho bạn xử lý. True nếu đã sang thanh toán."""
    popup = zone_popup(page)
    if not _visible(popup):
        return False
    try:
        title = popup.inner_text(timeout=1000).split("\n")[0].strip()
    except Exception:
        title = "Zone bạn chọn"
    result = finish_popup(page, popup, quantity, title)
    if result == "left":
        return True
    if result == "soldout":
        print("Zone này không chọn được vé – để pop-up cho bạn tự đóng / chọn zone khác...")
        while _visible(zone_popup(page)):
            nap(0.5)
    return left_ticket_page(page)


# Thời gian tối đa chờ sơ đồ + dữ liệu zone tải xong (giây). Chỉ là mức trần: dữ liệu về lúc nào thì đi tiếp lúc đó.
MAP_READY_TIMEOUT = 60


def wait_map_ready(page: Page, seconds: float = MAP_READY_TIMEOUT) -> dict:
    """Tiêu đề "Chọn khu vực" hiện trước, sơ đồ Konva và dữ liệu zone tải sau (không có CAPTCHA thì vào sơ đồ rất sớm).
    Chờ tới khi sơ đồ có zone và đọc được tên zone; trả về {mã zone: [tên...]} (rỗng nếu hết giờ)."""
    deadline = time.time() + seconds
    names: dict = {}
    while time.time() < deadline:
        if _visible(zone_popup(page)):     # bạn đã tự bấm zone trong lúc chờ -> xử lý pop-up luôn, khỏi chờ tiếp
            return section_names(page)
        try:
            ids = page.evaluate(_SECTION_IDS_JS)
        except Exception:
            ids = []
        if ids:
            names = section_names(page)
            if names:
                return names
        nap(0.2)
    print("  Sơ đồ / dữ liệu zone chưa tải xong sau %d giây." % seconds)
    return names


def typed_stop() -> bool:
    """Bạn có gõ "huy" + Enter trong terminal không (đọc không chặn; dòng gõ khác thì bỏ qua)."""
    import select
    try:
        while select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline()
            if not line:
                return False
            if _plain(line).strip() == "huy":
                return True
    except Exception:
        pass
    return False


def pick_zone(page: Page, zones: list[str], quantity: int, profile: str = "") -> bool:
    names = wait_map_ready(page)
    print(f"Canh vé tối đa {ZONE_RETRY_TIMEOUT // 60} phút – gõ 'huy' + Enter để dừng canh và tự chọn zone.")
    deadline = time.time() + ZONE_RETRY_TIMEOUT
    round_no = 0
    print("Zone đọc được từ dữ liệu trang:", ", ".join(f"{k}={_zone_label(v)}" for k, v in sorted(names.items())) or "(không có)")
    try:
        import json, pathlib
        pathlib.Path("debug", f"sections_{pathlib.Path(profile).name or 'x'}.json").write_text(json.dumps({
            "sections": names, "responses": [r.url for r in _json_responses]}, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    last_summary = None
    last_round_note = 0.0
    while time.time() < deadline:
        round_no += 1
        found_any = False
        # Quét trạng thái trước: zone còn vé thử trước (giữ thứ tự bạn ghi), zone hết vé dồn xuống cuối
        # (vẫn thử nhanh phòng có người nhả vé). Dữ liệu đọc lại mỗi vòng vì trang có thể cập nhật.
        names = section_names(page) or names
        states = zone_states(names, zones)
        ordered = ([z for z in zones if states[z] == "open"] + [z for z in zones if states[z] == "unknown"]
                   + [z for z in zones if states[z] == "soldout"])
        summary = ", ".join(f"{z}{' [hết]' if states[z] == 'soldout' else ' [?]' if states[z] == 'unknown' else ''}"
                            for z in ordered)
        if summary != last_summary:
            print("Thứ tự thử:", summary)
            last_summary = summary
        for zone in ordered:
            if typed_stop():
                print("Bạn gõ 'huy' – dừng canh vé.")
                return False
            try:
                if is_captcha(page):
                    wait_for_captcha_solved(page)
                if wait_other_dialog(page):
                    names = section_names(page) or names
                if left_ticket_page(page) or handle_user_popup(page, quantity):
                    return True
                popup, n_points = click_zone(page, zone, names,
                                             POPUP_WAIT_OPEN if states[zone] == "open" else POPUP_WAIT_SOLDOUT)
                found_any = found_any or n_points > 0
                if not popup:
                    print(f"Zone '{zone}': " + ("bấm rồi nhưng không mở pop-up (có thể hết vé)." if n_points
                                                 else "không tìm thấy trên sơ đồ."))
                    continue
                result = finish_popup(page, popup, quantity, f"Zone '{zone}'")
                if result == "left":
                    return True
                if result == "soldout" and _visible(zone_popup(page)):
                    close_zone_popup(page, zone_popup(page))
            except KeyboardInterrupt:
                raise
            except Exception as e:
                found_any = True
                print(f"Zone '{zone}': lỗi {type(e).__name__}: {str(e).splitlines()[0][:150]} – thử tiếp.")
        if not found_any:
            print("Không tìm thấy zone nào trong ZONES trên sơ đồ – giao lại cho bạn (xem debug/konva_*.json).")
            return False
        if round_no == 1 or time.time() - last_round_note > 60:   # canh tới 20 phút: không in mỗi vòng
            left = int(deadline - time.time())
            print(f"Hết vòng {round_no}, vẫn canh vé nhả (còn {left // 60} phút {left % 60} giây; gõ 'huy' để dừng)...")
            last_round_note = time.time()
        nap(0.5)
    return False


# ---------- Bảng câu hỏi (trước bước thanh toán) ----------
# Gắn nhãn cho từng ô nhập: nhãn = chữ của vùng lớn nhất quanh ô mà chỉ chứa đúng ô đó
# ("Họ & tên / Full name", "Số điện thoại/Căn cước công dân", "Email"...). Không dựa vào thứ tự ô.
_FORM_FIELDS_JS = """() => {
    const inputs = [...document.querySelectorAll('input, textarea')].filter(e => {
        const t = (e.getAttribute('type') || 'text').toLowerCase();
        if (e.tagName !== 'TEXTAREA' && !['text', 'tel', 'email', 'number'].includes(t)) return false;
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && !e.readOnly && !e.disabled && !e.closest('header');
    });
    return inputs.map((e, i) => {
        let c = e.parentElement, label = '';
        while (c && c !== document.body && c.querySelectorAll('input, textarea').length === 1) {
            const t = (c.innerText || '').trim();
            if (t) label = t;
            c = c.parentElement;
        }
        e.setAttribute('data-tbx-q', String(i));
        return {i, label: (label || e.placeholder || e.name || '').replace(/\\s+/g, ' ').slice(0, 160),
                required: /\\*/.test(label), value: e.value || ''};
    });
}"""

# Ô "đồng ý" (radio / checkbox): bấm vào nhãn của ô nếu chưa chọn. Trả về số ô đã chọn được.
_AGREE_JS = """() => {
    let n = 0;
    for (const e of document.querySelectorAll("input[type='checkbox'], input[type='radio']")) {
        let c = e, txt = '';
        for (let k = 0; k < 6 && c; k++, c = c.parentElement) { txt = c.innerText || ''; if (/đồng ý|agree/i.test(txt)) break; }
        if (!/đồng ý|agree/i.test(txt)) continue;
        if (!e.checked) (e.closest('label') || e).click();
        if (e.checked) n++;
    }
    return n;
}"""

_FIELD_RULES = [   # so trên nhãn đã bỏ dấu; thứ tự quan trọng: email trước, rồi điện thoại/CCCD, rồi họ tên
    ("email", re.compile(r"e-?mail", re.I)),
    ("phone", re.compile(r"dien thoai|phone|can cuoc|cccd|cmnd|citizen|\bid\b", re.I)),
    ("fullname", re.compile(r"ho\s*(&|va)?\s*ten|full\s*name|ten nguoi mua|\bname\b", re.I)),
]
# Ô xuất hoá đơn không bắt buộc: để trống (điền nửa chừng có thể bị đòi điền nốt tên công ty, mã số thuế...)
_INVOICE_RX = re.compile(r"hoa don|invoice|\bvat\b|ma so thue", re.I)


def _plain(text: str) -> str:
    """Bỏ dấu tiếng Việt, chữ thường: "Số điện thoại" -> "so dien thoai"."""
    text = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").replace("đ", "d").replace("Đ", "D").lower()


# Câu hỏi dạng chọn (radio / checkbox) trong form Ant Design (.ant-form-item). Bắt buộc = nhãn có
# .ant-form-item-required hoặc nhóm có aria-required. Câu bắt buộc chưa chọn: radio -> chọn lựa chọn kiểu
# "đồng ý / xác nhận / đã đọc / có" (câu về hoá đơn thì ưu tiên "không"), không có thì lựa chọn đầu; checkbox -> tích hết.
_REQUIRED_CHOICES_JS = """() => {
    const plain = t => (t || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase().trim();
    const out = [];
    for (const it of document.querySelectorAll('.ant-form-item')) {
        const label = ((it.querySelector('.ant-form-item-label') || it).innerText || '').replace(/\\s+/g, ' ').trim();
        const required = !!it.querySelector('.ant-form-item-required, [aria-required="true"]');
        const radios = [...it.querySelectorAll("input[type='radio']")];
        const boxes = [...it.querySelectorAll("input[type='checkbox']")];
        const agreeQ = /dong y|agree/.test(plain(it.innerText));
        const optText = e => ((e.closest('label') || e.parentElement).innerText || '').trim();
        if (radios.length && !radios.some(r => r.checked) && (required || agreeQ)) {
            const opts = radios.map(r => ({r, t: plain(optText(r))}));
            const invoiceQ = /hoa don|invoice|vat/.test(plain(label));
            const pick = (invoiceQ && opts.find(o => /^(khong|no)\\b/.test(o.t)))
                      || opts.find(o => /dong y|xac nhan|da doc|^co\\b|yes|agree|confirm/.test(o.t)) || opts[0];
            (pick.r.closest('label') || pick.r).click();
            out.push(label.slice(0, 60) + ' -> ' + optText(pick.r).slice(0, 50));
        }
        if (boxes.length && (required || agreeQ)) {
            for (const b of boxes) if (!b.checked) { (b.closest('label') || b).click(); out.push(label.slice(0, 60) + ' -> tích "' + optText(b).slice(0, 40) + '"'); }
        }
    }
    return out;
}"""

# Câu bắt buộc còn trống (để biết form đã đủ chưa trước khi bấm Tiếp tục).
_FORM_MISSING_JS = """() => {
    const out = [];
    for (const it of document.querySelectorAll('.ant-form-item')) {
        if (!it.querySelector('.ant-form-item-required, [aria-required="true"]')) continue;
        const label = ((it.querySelector('.ant-form-item-label') || it).innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 60);
        const choices = it.querySelectorAll("input[type='radio'], input[type='checkbox']");
        if (choices.length) { if (![...choices].some(c => c.checked)) out.push(label); continue; }
        const txt = it.querySelector("input:not([type='radio']):not([type='checkbox']):not([type='hidden']), textarea");
        if (txt && !txt.value.trim()) out.push(label);
    }
    return out;
}"""


def is_questionnaire(page: Page) -> bool:
    # Địa chỉ trang thật: .../bookings/<id>/question-form
    return "question" in page.url.lower() or _visible(page.get_by_text(re.compile(r"bảng\s*câu\s*hỏi", re.I)))


def fill_questionnaire(page: Page, info: dict) -> None:
    """Điền ô chữ (họ tên / SĐT / email), trả lời câu chọn bắt buộc, tích "đồng ý"."""
    fields = page.evaluate(_FORM_FIELDS_JS)
    for f in fields:
        label = _plain(f["label"])
        if not f["required"] and _INVOICE_RX.search(label):
            print(f"  Bỏ qua '{f['label'][:50]}' (không bắt buộc, xuất hoá đơn)")
            continue
        kind = next((k for k, rx in _FIELD_RULES if rx.search(label)), None)
        if kind and info.get(kind):
            page.locator(f'[data-tbx-q="{f["i"]}"]').fill(info[kind])
            print(f"  Điền '{f['label'][:50]}' = {info[kind]}")
        elif f["required"] and not f["value"]:
            print(f"  Không biết điền gì cho ô bắt buộc '{f['label'][:60]}'")
    for line in page.evaluate(_REQUIRED_CHOICES_JS):
        print(f"  Chọn: {line}")
    agree_text = page.get_by_text(re.compile(r"^\s*tôi đồng ý\s*$", re.I))
    if _visible(agree_text) and page.evaluate(_FORM_MISSING_JS):
        agree_text.first.click()
    page.evaluate(_AGREE_JS)          # form không theo mẫu Ant Design: vẫn tích các ô "đồng ý"


# Ảnh chụp giá trị mọi ô trong form – để biết bạn đã ngừng gõ chưa.
_FORM_SNAPSHOT_JS = """() => [...document.querySelectorAll('input, textarea')]
    .map(e => (e.type === 'radio' || e.type === 'checkbox') ? (e.checked ? '1' : '0') : e.value).join('\\u0001')"""
# Bạn đang tự sửa form: chỉ bấm Tiếp tục khi mọi câu bắt buộc đã có trả lời VÀ form đứng yên chừng này giây
# (tránh bấm khi bạn mới gõ được vài chữ ở ô cuối).
FORM_IDLE_SECONDS = 2.0


def submit_questionnaire(page: Page, info: dict) -> bool:
    """Điền rồi bấm Tiếp tục. Chưa qua được thì nhờ bạn sửa, và TỰ BẤM LẠI khi form đã đủ. True nếu đã qua."""
    fill_questionnaire(page, info)
    cont = page_button(page, TEXT_CONTINUE)
    started, no_button_warned = time.time(), False
    last_click, last_missing, warned = 0.0, None, False
    user_editing = False                      # đã từng phải nhờ bạn sửa -> chờ form đứng yên rồi mới bấm
    snap, snap_since = None, time.time()
    while is_questionnaire(page):
        if is_captcha(page):
            wait_for_captcha_solved(page)
            continue
        now_snap = page.evaluate(_FORM_SNAPSHOT_JS)
        if now_snap != snap:
            snap, snap_since = now_snap, time.time()
        missing = page.evaluate(_FORM_MISSING_JS)
        if missing:
            user_editing = True
            if missing != last_missing:
                beep()
                print(f"\n>>> Còn câu bắt buộc chưa trả lời: {missing}. Hãy tự trả lời – xong script tự bấm Tiếp tục.")
                last_missing = missing
        elif user_editing and time.time() - snap_since < FORM_IDLE_SECONDS:
            pass                              # bạn còn đang gõ
        elif not last_click and not _ready(cont) and time.time() - started > 6 and not no_button_warned:
            beep()
            print("\n>>> Form đã đủ nhưng script chưa bấm được nút 'Tiếp tục' – hãy tự bấm. Script chờ, sang trang sau thì chạy tiếp.")
            no_button_warned = True
        elif _ready(cont) and time.time() - last_click > 4:
            if last_click:
                print("  Bấm lại Tiếp tục")
            else:
                print("  Bấm Tiếp tục")
            cont.click(timeout=3000, no_wait_after=True)
            last_click = time.time()
            last_missing = None
        elif last_click and time.time() - last_click > 4 and not warned:
            beep()
            print("\n>>> Đã bấm Tiếp tục nhưng trang chưa cho đi tiếp (có ô báo lỗi?). Hãy kiểm tra – sửa xong script tự bấm lại.")
            warned = True
            user_editing = True
        nap(0.5)
    return True


def pass_questionnaire(page: Page, info: dict) -> None:
    """Nếu sau bước chọn vé có Bảng câu hỏi thì tự điền; xong (hoặc không có) thì về để báo thanh toán."""
    deadline = time.time() + 20
    while time.time() < deadline and not is_questionnaire(page):
        if is_captcha(page):
            wait_for_captcha_solved(page)
        nap(0.3)
    if not is_questionnaire(page):
        return
    print("\nĐang điền Bảng câu hỏi...")
    nap(1)   # chờ form hiện đủ các ô
    dump_page(page, "form", "")
    submit_questionnaire(page, info)


# ---------- Trang Thanh toán (.../payment-info) ----------
# Chọn phương thức, tích ô đồng ý điều khoản, bấm "Thanh toán". Thông tin thẻ bạn tự nhập ở trang sau.
# Ô radio của từng phương thức: vùng nhỏ nhất quanh ô chỉ chứa đúng 1 ô radio = một dòng phương thức.
_PAYMENT_CHECKED_JS = """(target) => {
    const norm = t => (t || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/[đĐ]/g, 'd')
                                  .replace(/[\\s_()\\-\\/]+/g, '').toLowerCase();
    for (const r of document.querySelectorAll("input[type='radio']")) {
        let c = r;
        while (c.parentElement && c.parentElement.querySelectorAll("input[type='radio']").length === 1) c = c.parentElement;
        if (norm(c.innerText).includes(target)) return r.checked;
    }
    return null;
}"""


TEXT_PAY = re.compile(r"^\s*thanh\s*toán\s*$", re.I)


def page_button(page: Page, rx):
    """Nút ĐANG HIỆN có chữ khớp rx. Tìm theo chữ trên nút, không theo "vai trò + tên" (get_by_role): trên trang thật
    có lúc tìm theo vai trò không ra nút Thanh toán dù nút nằm ngay đó."""
    return page.locator("button").filter(has_text=rx).filter(visible=True).last


def _clickable(btn) -> bool:
    try:
        return btn.count() > 0 and btn.is_enabled(timeout=1000)
    except Exception:
        return False


def is_payment_page(page: Page) -> bool:
    return "payment" in page.url.lower()


def bin_popup(page: Page):
    # Đợt presale Techcombank: sau khi bấm Thanh toán hiện "Nhập số thẻ để kiểm tra" – "6 số đầu" – Hủy / Xác nhận.
    return page.locator("[role='dialog'], .ant-modal, .tbox-modal, .ant-drawer").filter(
        has_text=re.compile(r"nhập số thẻ|6 số đầu", re.I)).last


def tick_bin_agree(page: Page, popup, ok) -> None:
    """Tích ô "Bằng việc tích chọn, bạn xác nhận đã đọc, hiểu và đồng ý..." trong pop-up BIN.
    Ô này có thể là checkbox thật, checkbox tự vẽ, hoặc chỉ là ô vuông cạnh chữ -> thử lần lượt từng cách,
    sau mỗi cách xem nút Xác nhận đã sáng chưa (sáng = đã tích được, dừng)."""
    def ready() -> bool:
        nap(0.3)
        return _visible(ok) and ok.is_enabled()

    if ready():
        return
    boxes = popup.locator("input[type='checkbox']")
    for k in range(boxes.count()):                       # 1. checkbox thật (kể cả bị ẩn): bấm nhãn bọc ngoài
        box = boxes.nth(k)
        try:
            if not box.is_checked(timeout=1000):
                wrapper = box.locator("xpath=ancestor::label[1]")
                (wrapper if wrapper.count() else box).click(force=True, timeout=2000)
        except Exception:
            pass
        if ready():
            return
    fake = popup.locator("[role='checkbox'], .ant-checkbox, [class*='checkbox' i], [class*='check-box' i]")
    for k in range(min(fake.count(), 3)):                # 2. checkbox tự vẽ
        try:
            fake.nth(k).click(force=True, timeout=2000)
        except Exception:
            pass
        if ready():
            return
    txt = popup.get_by_text(re.compile(r"bằng việc tích chọn", re.I))
    if _visible(txt):
        box = txt.first.bounding_box(timeout=1000)
        if box:                                          # 3. ô vuông nằm ngay bên trái dòng chữ
            page.mouse.click(box["x"] - 16, box["y"] + 11)
            if ready():
                return
        txt.first.click(position={"x": 2, "y": 8})       # 4. bấm đầu dòng chữ (nếu chữ nằm trong nhãn của ô)
        if ready():
            return
    try:
        import pathlib
        pathlib.Path("debug").mkdir(exist_ok=True)
        pathlib.Path("debug", "bin_popup.html").write_text(popup.evaluate("e => e.outerHTML", timeout=2000), encoding="utf-8")
    except Exception:
        pass


def handle_bin_popup(page: Page, card_bin: str) -> None:
    popup = bin_popup(page)
    digits = re.sub(r"\D", "", card_bin or "")
    if len(digits) != 6:
        beep()
        print("\n>>> Pop-up kiểm tra đầu thẻ (BIN) – CARD_BIN trong run_dayX.sh chưa có 6 số. Hãy tự nhập, tích ô và Xác nhận.")
        while _visible(bin_popup(page)):
            nap(0.5)
        return
    print(f"  Pop-up kiểm tra đầu thẻ: nhập {digits}")
    # Ô "6 số đầu" có thể là 1 ô hoặc 6 ô nhỏ tự nhảy: bấm ô đầu rồi gõ từng số.
    first = popup.locator("input:not([type='checkbox']):not([type='radio'])").first
    first.click()
    page.keyboard.type(digits, delay=60)
    ok = popup.locator("button").filter(has_text=re.compile(r"^\s*xác\s*nhận\s*$", re.I)).filter(visible=True).last
    tick_bin_agree(page, popup, ok)
    deadline = time.time() + 5
    while time.time() < deadline and not (_visible(ok) and ok.is_enabled()):
        nap(0.2)
    if _visible(ok) and ok.is_enabled():
        print("  Bấm Xác nhận")
        ok.click(timeout=3000, no_wait_after=True)
    else:
        beep()
        print("\n>>> Nút Xác nhận ở pop-up kiểm tra đầu thẻ chưa bấm được – hãy kiểm tra 6 số và ô đồng ý rồi tự bấm.")
    deadline = time.time() + 120
    while time.time() < deadline and _visible(bin_popup(page)):
        nap(0.3)


def start_payment(page: Page, method: str, card_bin: str = "") -> bool:
    """True nếu đã bấm Thanh toán và trang đã chuyển sang bước nhập thẻ / cổng thanh toán."""
    deadline = time.time() + 20
    while time.time() < deadline and not is_payment_page(page):
        nap(0.3)
    if not is_payment_page(page):
        return False
    nap(1)   # chờ trang hiện đủ
    dump_page(page, "payment", "")
    if method:
        opt = page.get_by_text(re.compile(r"\s*".join(map(re.escape, method.split())), re.I))
        if not _visible(opt):
            beep()
            print(f"\n>>> Không thấy phương thức '{method}' trên trang – hãy tự chọn phương thức thanh toán.")
            return click_pay_and_wait(page, card_bin)
        opt.first.click()
        nap(0.3)
        checked = page.evaluate(_PAYMENT_CHECKED_JS, _norm(method).replace("/", ""))
        print(f"  Chọn phương thức '{method}'" + ("" if checked is not False else " – CHƯA chọn được!"))
        if checked is False:
            beep()
            print(f"\n>>> Chưa chọn được '{method}' – hãy tự chọn phương thức thanh toán.")
            return click_pay_and_wait(page, card_bin)
    agreed = page.evaluate(_AGREE_JS)
    print(f"  Đã tích {agreed} ô đồng ý điều khoản." if agreed else "  Không thấy ô đồng ý điều khoản (bỏ qua).")
    return click_pay_and_wait(page, card_bin)


def click_pay_and_wait(page: Page, card_bin: str) -> bool:
    """Bấm "Thanh toán" rồi chờ tới khi THẬT SỰ rời trang thanh toán (sang cổng nhập thẻ / mở tab mới).
    Không bấm được thì nhờ bạn bấm tay; trong lúc chờ vẫn lo CAPTCHA và pop-up kiểm tra đầu thẻ. Không có giới hạn
    thời gian: chỉ báo "nhập thẻ" khi trang đã chuyển."""
    url, n_pages = page.url, len(page.context.pages)
    pay = page_button(page, TEXT_PAY)
    deadline = time.time() + 10
    while time.time() < deadline and not _clickable(pay):
        nap(0.2)
    clicked = _clickable(pay)
    if clicked:
        print("  Bấm Thanh toán")
        pay.click(timeout=3000, no_wait_after=True)
    else:
        dump_page(page, "payment_fail", "")      # lưu đúng lúc không bấm được để tìm nguyên nhân
        try:
            info = page.evaluate("""() => [...document.querySelectorAll('button')].filter(b => /thanh\\s*toán/i.test(b.innerText))
                .map(b => ({text: b.innerText.trim(), disabled: b.disabled, visible: !!b.offsetParent}))""")
            print("  Nút 'Thanh toán' trên trang:", info)
        except Exception:
            pass
        beep()
        print("\n>>> Script CHƯA bấm được nút 'Thanh toán' – hãy tự bấm 'Thanh toán' trong Chrome.\n"
              "    Script vẫn lo CAPTCHA / pop-up kiểm tra đầu thẻ, và báo khi trang đã sang bước nhập thẻ.")
    since, warned = time.time(), False
    while True:
        nap(0.3)
        if is_captcha(page):
            wait_for_captcha_solved(page)
            since = time.time()
        elif _visible(bin_popup(page)):
            handle_bin_popup(page, card_bin)
            since = time.time()
        elif (page.url != url and "payment-info" not in page.url) or len(page.context.pages) > n_pages:
            return True
        elif clicked and not warned and time.time() - since > 20:
            beep()
            print("\n>>> Đã bấm 'Thanh toán' 20 giây mà trang chưa chuyển – hãy nhìn màn hình (có báo lỗi?) và tự xử lý.\n"
                  "    Script vẫn chờ, trang sang bước nhập thẻ thì báo.")
            warned = True


def dump_page(page: Page, kind: str, profile: str) -> None:
    # Lưu HTML trang (sơ đồ / CAPTCHA) để chỉnh script khi có trục trặc: debug/<kind>_<profile>.html
    try:
        import pathlib
        out = pathlib.Path("debug") / f"{kind}_{pathlib.Path(profile).name or 'x'}.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(page.content(), encoding="utf-8")
    except Exception as e:
        print("Không lưu được sơ đồ:", e)


def buy_one(page: Page, args, showtime: str) -> None:
    """Một đơn: bấm Mua vé đúng ngày -> mã presale / CAPTCHA / hàng chờ -> zone -> Bảng câu hỏi -> Thanh toán."""
    zones = args.zone
    _json_responses.clear()          # dữ liệu sơ đồ của đơn trước không dùng lại
    wait_for_buy_button(page, args.event_url, [showtime])

    if pass_gates_until_ticket_page(page, args.code, args.profile):
        wait_map_ready(page)
        dump_page(page, "map", args.profile)
        names = map_zone_names(page)
        try:
            import json, pathlib
            pathlib.Path("debug", f"konva_{pathlib.Path(args.profile).name}.json").write_text(
                json.dumps(page.evaluate(_KONVA_DUMP_JS), ensure_ascii=False, indent=1), encoding="utf-8")
            pathlib.Path("debug", f"zones_{pathlib.Path(args.profile).name}.json").write_text(
                json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            print("Không lưu được cấu trúc sơ đồ:", e)
        print("Đã vào sơ đồ chọn khu vực, script tự bấm zone...")
        if not pick_zone(page, zones, args.qty, args.profile):
            wait_until_left_ticket_page(page, "Script không chọn được zone nào. Hãy tự BẤM VÀO ZONE còn sáng trên sơ đồ – "
                                              "script sẽ tự chọn số lượng và bấm Tiếp tục.", args.qty)
    else:
        wait_until_left_ticket_page(page, "Quá lâu chưa tới sơ đồ chọn vé. Hãy tự xử lý tiếp trong Chrome.")

    pass_questionnaire(page, {"fullname": args.fullname, "phone": args.phone, "email": args.email})
    while is_questionnaire(page) or not left_ticket_page(page):   # chưa qua thì chờ, không báo bừa
        nap(0.5)
    print("\nĐang ở trang Thanh toán...")
    on_gateway = start_payment(page, args.payment, args.card_bin)
    beep()
    if on_gateway:
        print(f"\n>>> [{showtime}] Đã sang bước nhập thẻ. HÃY TỰ NHẬP THÔNG TIN THẺ và hoàn tất "
              "(vé chỉ được giữ trong thời gian ngắn!).")
    else:
        print(f"\n>>> [{showtime}] Script không thấy trang Thanh toán – hãy nhìn màn hình và tự hoàn tất "
              "(vé chỉ được giữ trong thời gian ngắn!).")


def next_or_close(done: str, nxt: str) -> bool:
    """Sau một đơn: 'tiep' = mua ngày tiếp theo trong cùng cửa sổ, 'xong' = dừng. True nếu mua tiếp."""
    while True:
        a = ask(f"\n{done} – thanh toán XONG đơn này thì gõ 'tiep' để mua tiếp {nxt} (cùng mã), "
                "hoặc 'xong' để dừng: ").strip().lower()
        if a in ("tiep", "tiếp"):
            return True
        if a == "xong":
            return False
        print("  (Gõ 'tiep' hoặc 'xong'. Chrome vẫn mở.)")


def run_orders(page: Page, args, open_at) -> None:
    """Mua lần lượt từng ngày trong --showtime, cùng một tài khoản và cùng một mã presale."""
    showtimes = args.showtime
    for k, showtime in enumerate(showtimes):
        print(f"\n========== Đơn {k + 1}/{len(showtimes)}: {showtime} ==========")
        if k == 0:
            wait_until(open_at)
        try:
            buy_one(page, args, showtime)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            # Lỗi bất ngờ: KHÔNG đóng Chrome (đóng là mất lượt mua) – giao cho bạn làm tiếp bằng tay.
            import traceback
            traceback.print_exc()
            beep()
            print(f"\n>>> Script gặp lỗi ({type(e).__name__}) ở đơn {showtime} nhưng Chrome vẫn mở – hãy tự làm tiếp trong Chrome.")
        if k + 1 < len(showtimes) and not next_or_close(f"Đơn {showtime}", showtimes[k + 1]):
            return


def main() -> None:
    ap = argparse.ArgumentParser(description="Ticketbox helper – thường chạy qua run_day1.sh")
    ap.add_argument("--profile", required=True, help="Thư mục profile Chrome = 1 tài khoản, vd ./chrome-acc1")
    ap.add_argument("--showtime", action="append", required=True,
                    help="Ngày muốn mua, giống dòng trong 'Lịch diễn'. Lặp lại để mua lần lượt nhiều ngày, "
                         "vd --showtime '03 Tháng 12' --showtime '04 Tháng 12'")
    ap.add_argument("--zone", action="append", required=True,
                    help="Zone trên sơ đồ, lặp lại theo thứ tự ưu tiên, vd --zone 'ĐỈNH NÓC' --zone 'SỤC SÔI'")
    ap.add_argument("--qty", type=int, required=True, help="Số vé")
    ap.add_argument("--code", default="", help="Mã presale / early bird (dùng lại cho mọi ngày)")
    ap.add_argument("--fullname", default="", help="Họ tên điền Bảng câu hỏi")
    ap.add_argument("--phone", default="", help="Số điện thoại (điền cả ô 'Số điện thoại/Căn cước công dân')")
    ap.add_argument("--email", default="", help="Email điền Bảng câu hỏi")
    ap.add_argument("--payment", default="", help="Phương thức thanh toán chọn sẵn, vd 'Thẻ ghi nợ/Thẻ tín dụng'")
    ap.add_argument("--card-bin", default="", help="6 số đầu thẻ cho pop-up kiểm tra BIN (đợt presale Techcombank)")
    ap.add_argument("--event-url", default=EVENT_URL)
    ap.add_argument("--open-at", default=OPEN_AT, help="'YYYY-MM-DD HH:MM:SS', hoặc '' nếu đang bán")
    args = ap.parse_args()

    open_at = dt.datetime.strptime(args.open_at, "%Y-%m-%d %H:%M:%S") if args.open_at else None
    print(f"Profile: {args.profile}\nSự kiện: {args.event_url}\nZone ưu tiên: {args.zone} x{args.qty}\n"
          f"Mua lần lượt: {' -> '.join(args.showtime)}\n"
          f"Mở bán: {open_at or 'ngay'}\nMã presale: {'có' if args.code else 'không'}\n")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            args.profile, channel="chrome", headless=False, no_viewport=True,
            chromium_sandbox=True,  # Playwright mặc định thêm --no-sandbox; bật lại sandbox cho an toàn
            # Playwright mặc định dùng keychain giả, nên không giải mã được cookie mà Chrome thường
            # (login.sh) đã lưu bằng Keychain thật -> mất phiên đăng nhập. Dùng Keychain thật.
            ignore_default_args=["--use-mock-keychain", "--password-store=basic"],
            # Ctrl+C mà để Playwright tự giết Chrome thì cookie (phiên đăng nhập) chưa kịp ghi xuống đĩa
            # -> mất đăng nhập. Tự bắt Ctrl+C bên dưới và đóng Chrome bình thường.
            handle_sigint=False,
        )
        ctx.set_default_timeout(5000)              # thao tác không ghi thời gian chờ: tối đa 5 giây (mặc định 30)
        ctx.set_default_navigation_timeout(60000)  # tải trang: 60 giây (ngày mở bán Ticketbox có thể chậm)
        signal.signal(signal.SIGINT, _on_sigint)
        try:
            record_json_responses(ctx)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            ensure_logged_in(page)
            run_orders(page, args, open_at)
            confirm_close("Thanh toán xong")
        except KeyboardInterrupt:
            print("\nĐang đóng Chrome cho đàng hoàng để giữ phiên đăng nhập, chờ vài giây...")
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
