"""Vẽ sơ đồ ghế có ghi tên từng ghế (HÀNG-SỐ, vd A3-16) từ dữ liệu `seat_inspect.py` đã lưu.

Chạy: python seat_labels.py [debug/seats_<mã sự kiện>]   ->  <thư mục đó>/seat_labels.html (mặc định: lần xem ghế mới nhất)
Ghế đỏ = đã bán / không chọn được lúc chạy xem ghế. Tên ghế dùng để ghi vào SEATS.

Sơ đồ CHUNG cho một lầu (không trạng thái ghế, không tên hạng / giá – mỗi sự kiện đặt khác nhau):
  python seat_labels.py debug/seats_26708 --generic "Bến Thành – Lầu 1" --out seatmaps/ben_thanh_lau1.html
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib


def latest_dir() -> pathlib.Path:
    dirs = sorted(pathlib.Path("debug").glob("seats*/"), key=lambda d: d.stat().st_mtime)
    if not dirs:
        raise SystemExit("Chưa có dữ liệu sơ đồ – chạy ./inspect_seats.sh trước.")
    return dirs[-1]


def load_seatmap(folder: pathlib.Path) -> dict:
    for f in sorted(folder.glob("api_*_seatmap.json")):
        return json.loads(f.read_text(encoding="utf-8"))["body"]["data"]["result"]
    raise SystemExit(f"Không có dữ liệu sơ đồ trong {folder} – chạy ./inspect_seats.sh trước.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", type=pathlib.Path)
    ap.add_argument("--generic", metavar="TIÊU ĐỀ", help="vẽ sơ đồ chung của lầu: mọi ghế trắng, không tên hạng / giá")
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args()
    folder = args.folder or latest_dir()
    generic = args.generic is not None
    m = load_seatmap(folder)
    vb = m.get("viewbox") or "0 0 800 400"
    parts, legend, n_free, n_sold = [], {}, 0, 0
    for k, s in enumerate(m["sections"]):
        tt = s.get("ticketType") or {}
        if tt:
            legend[tt["name"]] = (tt.get("color") or "#888", tt.get("price") or 0)
        for e in s.get("elements") or []:
            if e.get("type") == "path" and e.get("data"):
                if s.get("isStage") or not tt:
                    fill, op = e.get("fill"), ""
                elif generic:      # khối ghế: xám xen kẽ để phân biệt các khối, không theo hạng vé
                    fill, op = ("#8a8f9c" if k % 2 else "#a3a8b5"), ' stroke="#fff" stroke-width="0.6"'
                else:
                    fill, op = tt.get("color"), ' fill-opacity="0.85"'
                parts.append(f'<path d="{e["data"]}" fill="{fill}"{op}/>')
    for s in m["sections"]:
        for r in s.get("rows") or []:
            for x in r["seats"]:
                free = generic or x["status"] == 1
                n_free += free
                n_sold += not free
                name = f'{r["name"]}-{x["name"]}'
                tip = html.escape(name if generic else f'{name} · {(s.get("ticketType") or {}).get("name", s["name"])} · '
                                                        f'{"trống" if free else "đã bán"}')
                parts.append(f'<g><title>{tip}</title><circle cx="{x["x"]}" cy="{x["y"]}" r="4.2" '
                             f'fill="{"#fff" if free else "#e8433b"}" stroke="#333" stroke-width="0.5"/>'
                             f'<text x="{x["x"]}" y="{x["y"] + 1.1}" class="{"f" if free else "s"}">{html.escape(name)}</text></g>')
    if generic:
        title = html.escape(args.generic)
        head = (f"<b>Sơ đồ chung – {title}</b> ({n_free} ghế). Tên ghế ghi trên từng chấm (HÀNG-SỐ), dùng để ghi vào SEATS.<br>"
                "Không có trạng thái ghế, tên hạng và giá (mỗi sự kiện mỗi khác – xem trên Ticketbox). "
                "Khối xám chỉ để phân biệt các khu ghế. Cuộn ngang / Cmd+ để phóng to.")
    else:
        title = "Sơ đồ ghế"
        leg = "".join(f'<span><i style="background:{c}"></i>{html.escape(n)} – {p:,}đ</span>'.replace(",", ".")
                      for n, (c, p) in sorted(legend.items(), key=lambda kv: -kv[1][1]))
        head = (f"<b>Sơ đồ ghế</b> – tên ghế ghi trên từng chấm (HÀNG-SỐ). Trắng = còn trống ({n_free}), đỏ = đã bán "
                f"({n_sold}) lúc chạy xem ghế. Di chuột lên ghế để xem hạng vé. Cuộn ngang / Cmd+ để phóng to.<br>{leg}")
    page = f"""<!doctype html><meta charset="utf-8"><title>{title}</title>
<style>body{{margin:0;background:#111;color:#eee;font:14px system-ui}} header{{padding:12px 16px}}
header span{{margin-right:18px;white-space:nowrap}} i{{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:6px}}
svg{{width:max(100vw,2200px);display:block;background:#000}} text{{font:700 2.6px system-ui;text-anchor:middle}}
text.f{{fill:#000}} text.s{{fill:#fff}}</style>
<header>{head}</header>
<svg viewBox="{vb}">{''.join(parts)}</svg>"""
    out = args.out or folder / "seat_labels.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"Đã vẽ {n_free + n_sold} ghế -> {out}")


if __name__ == "__main__":
    main()
