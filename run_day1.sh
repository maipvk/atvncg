#!/bin/zsh
# Tài khoản 1 – mua lần lượt các ngày trong SHOWTIMES. Cấu hình riêng của tài khoản này (link sự kiện + giờ mở bán chung nằm trong ticketbox_helper.py).
PROFILE="./chrome-acc1"
# Ngày muốn mua, ghi giống dòng trong "Lịch diễn". Nhiều ngày = mua LẦN LƯỢT trong cùng cửa sổ, cùng mã CODE (trong personal.local.sh):
# xong đơn ngày đầu (bạn thanh toán) thì gõ 'tiep' để script mua ngày kế tiếp. Ngày quan trọng hơn để trước.
SHOWTIMES=("28 Tháng 11")
ZONES=("ĐỘC BẢN" "NGÔI SAO 3" "DẤU ẤN 2" "NIÊN THIẾU 2") # ("ĐỈNH NÓC" "SỤC SÔI")      # zone theo thứ tự ưu tiên
QTY=1
# Phương thức thanh toán chọn sẵn (ghi giống chữ trên trang Thanh toán). Thông tin thẻ bạn tự nhập.
PAYMENT="Thẻ ghi nợ/Thẻ tín dụng"

cd "$(dirname "$0")" && source .venv/bin/activate
# Họ tên / SĐT / email / mã presale / 6 số đầu thẻ nằm trong personal.local.sh (không đẩy lên GitHub)
[[ -f personal.local.sh ]] || { echo "Thiếu personal.local.sh – chép personal.example.sh thành personal.local.sh rồi điền."; exit 1; }
source personal.local.sh
args=(--profile "$PROFILE" --qty "$QTY" --code "$CODE"
      --fullname "$FULLNAME" --phone "$PHONE" --email "$EMAIL" --payment "$PAYMENT"
      --card-bin "$CARD_BIN")
for d in "${SHOWTIMES[@]}"; do args+=(--showtime "$d"); done
for z in "${ZONES[@]}"; do args+=(--zone "$z"); done
python ticketbox_helper.py "${args[@]}"
