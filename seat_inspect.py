"""Xem ghế: vào trang chọn vé của một sự kiện có sơ đồ CHỌN TỪNG GHẾ và lưu lại dữ liệu sơ đồ, KHÔNG bấm ghế nào.

Dùng để biết tên / mã từng ghế trước khi ghi ghế muốn mua. Kết quả nằm trong debug/seats_<mã sự kiện>/:
  page.html      HTML trang chọn vé
  map.png        ảnh chụp sơ đồ
  api_*.json     dữ liệu Ticketbox tải về (danh sách ghế, hạng giá, trạng thái)
  shapes.json    các hình trên sơ đồ (Konva / SVG) kèm vị trí trên màn hình

Chạy: ./inspect_seats.sh <link sự kiện> "<ngày>" [chrome-accN]   (CAPTCHA thì giải như lúc mua; xong gõ 'xong')
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import signal

from playwright.sync_api import sync_playwright

import ticketbox_helper as th

OUT = pathlib.Path("debug", "seats")      # đổi thành debug/seats_<mã sự kiện> trong main()

# Mọi hình trên sơ đồ: Konva (canvas) và SVG, kèm khung trên màn hình. Không bấm gì.
_SHAPES_JS = """() => {
    const out = {konva: [], svg: [], dom: []};
    const plain = a => { const o = {}; for (const [k, v] of Object.entries(a || {})) {
        if (v == null || typeof v === 'function') continue;
        if (typeof v === 'object') { try { o[k] = JSON.parse(JSON.stringify(v)); } catch (e) {} }
        else o[k] = typeof v === 'string' && v.length > 300 ? v.slice(0, 300) + '…' : v; } return o; };
    for (const st of (window.Konva && window.Konva.stages) || []) {
        const box = st.container().getBoundingClientRect();
        for (const n of st.find(() => true)) {
            let r = null; try { r = n.getClientRect(); } catch (e) {}
            out.konva.push({cls: n.getClassName(), attrs: plain(n.attrs),
                rect: r && [box.left + r.x, box.top + r.y, r.width, r.height].map(v => Math.round(v * 10) / 10),
                parent: n.parent ? (n.parent.getAttr('id') || n.parent.getAttr('name') || n.parent.getClassName()) : null});
        }
    }
    for (const e of document.querySelectorAll('svg circle, svg rect, svg path, svg text, svg g[id], svg g[data-id]')) {
        const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue;
        const a = {}; for (const at of e.attributes) if (at.name !== 'd') a[at.name] = at.value.slice(0, 200);
        out.svg.push({tag: e.tagName, attrs: a, text: e.tagName === 'text' ? e.textContent : undefined,
            rect: [r.x, r.y, r.width, r.height].map(v => Math.round(v))});
    }
    for (const e of document.querySelectorAll('[data-seat], [data-seat-id], [data-id], [class*="seat" i]')) {
        const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue;
        const a = {}; for (const at of e.attributes) a[at.name] = at.value.slice(0, 200);
        out.dom.push({tag: e.tagName, attrs: a, text: (e.innerText || '').slice(0, 80), rect: [r.x, r.y, r.width, r.height].map(Math.round)});
    }
    out.counts = {konva: out.konva.length, svg: out.svg.length, dom: out.dom.length,
                  canvases: document.querySelectorAll('canvas').length};
    return out;
}"""


def save_map(page, out: pathlib.Path = OUT) -> None:
    """Lưu HTML, ảnh, các hình trên sơ đồ và dữ liệu JSON Ticketbox đã tải vào debug/seats/."""
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("api_*.json"):
        old.unlink()
    (out / "page.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(out / "map.png"), full_page=True)
    shapes = page.evaluate(_SHAPES_JS)
    (out / "shapes.json").write_text(json.dumps(shapes, ensure_ascii=False, indent=1), encoding="utf-8")
    saved = 0
    for i, r in enumerate(list(th._json_responses)):
        try:
            body = r.json()
        except Exception:
            continue
        name = re.sub(r"[^A-Za-z0-9]+", "_", r.url.split("?")[0].split("//", 1)[-1])[-80:]
        (out / f"api_{i:03d}_{name}.json").write_text(
            json.dumps({"url": r.url, "body": body}, ensure_ascii=False, indent=1), encoding="utf-8")
        saved += 1
    print(f"\nĐã lưu vào {out}/: page.html, map.png, shapes.json ({shapes['counts']}), {saved} file api_*.json.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--event-url", required=True)
    ap.add_argument("--showtime", default="")
    args = ap.parse_args()
    m = re.search(r"-(\d+)(?:[/?#]|$)", args.event_url)
    out = pathlib.Path("debug", f"seats_{m.group(1)}" if m else "seats")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            args.profile, channel="chrome", headless=False, no_viewport=True, chromium_sandbox=True,
            ignore_default_args=["--use-mock-keychain", "--password-store=basic"], handle_sigint=False)
        ctx.set_default_timeout(5000)
        ctx.set_default_navigation_timeout(60000)
        signal.signal(signal.SIGINT, th._on_sigint)
        try:
            th.record_json_responses(ctx)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            th.ensure_logged_in(page)
            th.wait_for_buy_button(page, args.event_url, [args.showtime])
            # Tới trang chọn vé (theo địa chỉ trang); CAPTCHA / mã presale / đăng nhập thì như lúc mua.
            tried: set[str] = set()
            while not ("select-ticket" in page.url and not th.is_captcha(page)):
                if th.is_login_modal(page):
                    th.pause_for_user("Ticketbox đòi đăng nhập. Hãy tự đăng nhập rồi tự bấm lại 'Mua vé ngay' nếu cần.")
                elif th.is_captcha(page):
                    th.wait_for_captcha_solved(page, args.profile)
                elif th.is_code_page(page):
                    th.handle_code_page(page, "", tried)
                th.nap(0.3)
            print("Đã vào trang chọn vé – chờ sơ đồ vẽ xong...")
            try:
                page.wait_for_function("() => document.querySelectorAll('canvas').length > 0 || "
                                       "document.querySelectorAll('svg circle').length > 20", timeout=30000)
            except Exception:
                print("  (không thấy canvas / svg sau 30 giây – vẫn lưu những gì đang có)")
            th.nap(3)

            save_map(page, out)
            print(f"Vẽ sơ đồ có tên ghế: python seat_labels.py {out}")
            print("Script KHÔNG bấm ghế nào. Gửi Claude biết là xong.")
            th.confirm_close("Xem xong")
        except KeyboardInterrupt:
            print("\nĐang đóng Chrome cho đàng hoàng để giữ phiên đăng nhập, chờ vài giây...")
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
