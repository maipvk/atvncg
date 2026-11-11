#!/bin/zsh
# Xem ghế: vào trang chọn vé của một sự kiện, lưu dữ liệu sơ đồ vào debug/seats_<mã sự kiện>/ (KHÔNG bấm ghế nào),
# rồi vẽ sơ đồ có ghi tên từng ghế (seat_labels.html trong thư mục đó).
# Cách dùng: ./inspect_seats.sh <link sự kiện> "<ngày như trong Lịch diễn>" [profile, mặc định chrome-acc1]
#   vd: ./inspect_seats.sh https://ticketbox.vn/the-starry-nhm-show-26676 "12 Tháng 11"
EVENT_URL="${1:?Thiếu link sự kiện, vd: ./inspect_seats.sh https://ticketbox.vn/ten-su-kien-12345 \"12 Tháng 11\"}"
SHOWTIME="${2:-}"
PROFILE="./${3:-chrome-acc1}"

cd "$(dirname "$0")" && source .venv/bin/activate
python seat_inspect.py --profile "$PROFILE" --event-url "$EVENT_URL" --showtime "$SHOWTIME" && python seat_labels.py
