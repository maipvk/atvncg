"""
Bản Windows của ticketbox_helper.py – run_day1.ps1 / run_day2.ps1 chạy file này thay cho ticketbox_helper.py.

Chạy ticketbox_helper.py y nguyên, chỉ thay vài chỗ cần riêng cho Windows ngay lúc chạy,
nên ticketbox_helper.py (dùng chung với macOS) không bị sửa gì.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ticketbox_helper as helper  # noqa: E402

_original_ensure_logged_in = helper.ensure_logged_in


def ensure_logged_in(page) -> None:
    # Cửa sổ Chrome hẹp (vd chia đôi màn hình) thì Ticketbox chỉ hiện ảnh đại diện, không có chữ "Tài khoản"
    # mà bản gốc dò tìm -> báo nhầm "chưa đăng nhập". Phóng to cửa sổ lúc kiểm tra rồi trả lại kích thước cũ.
    cdp = None
    try:
        cdp = page.context.new_cdp_session(page)
        window_id = cdp.send("Browser.getWindowForTarget")["windowId"]
        old = cdp.send("Browser.getWindowBounds", {"windowId": window_id})["bounds"]
        cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "maximized"}})
    except Exception:
        cdp = None
    try:
        _original_ensure_logged_in(page)
    finally:
        if cdp:
            try:
                if old.get("windowState", "normal") == "normal":
                    cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "normal"}})
                    cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {
                        k: old[k] for k in ("left", "top", "width", "height")}})
                else:
                    cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": old["windowState"]}})
            except Exception:
                pass


helper.ensure_logged_in = ensure_logged_in

if __name__ == "__main__":
    helper.main()
