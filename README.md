# Ticketbox helper

Script tự chạy: đếm ngược giờ mở bán, tải lại trang, bấm "Mua vé ngay" đúng ngày, điền mã early bird (nếu có),
chờ hàng chờ, bấm zone trên sơ đồ, chỉnh số lượng, bấm "Tiếp tục".
**Bạn** chỉ cần: đăng nhập (lần đầu), giải CAPTCHA khi nghe bíp, và thanh toán.

## Các file

| File | Là gì | Sửa gì |
|---|---|---|
| `ticketbox_helper.py` | Chương trình chính | Chỉ khối **CẤU HÌNH CHUNG** ở đầu: `EVENT_URL`, `OPEN_AT` |
| `run_day1.sh` | Tài khoản 1 (vd mua DAY 3) | `PROFILE`, `SHOWTIMES`, `ZONES`, `QTY`, `PAYMENT` |
| `run_day2.sh` | Tài khoản 2 (vd mua DAY 4), chạy song song | như trên |
| `personal.local.sh` | **Thông tin cá nhân**, chỉ có trên máy bạn (không đẩy lên GitHub) | `FULLNAME`, `PHONE`, `EMAIL`, `CODE`, `CARD_BIN` |
| `personal.example.sh` | File mẫu trống của `personal.local.sh` | Không sửa |
| `login.sh` | Mở Chrome thường với profile của script để đăng nhập bằng Google | Không sửa |

## Những gì KHÔNG có trên GitHub

Các file / thư mục sau nằm trong `.gitignore`: **vẫn giữ nguyên trên máy bạn**, chỉ không được đẩy lên GitHub.

| File / thư mục | Chứa gì |
|---|---|
| `personal.local.sh` | Họ tên, SĐT, email, mã presale, 6 số đầu thẻ |
| `chrome-acc1/`, `chrome-acc2/` | Phiên đăng nhập Ticketbox / Google của từng tài khoản – ai có thư mục này là vào được tài khoản |
| `debug/` | HTML các trang lưu lại khi chạy (có thông tin đặt vé), dùng để sửa lỗi |
| `.venv/` | Thư viện Python đã cài |

Sửa thông tin cá nhân hay mã presale thì sửa trong `personal.local.sh`; `run_day1.sh` và `run_day2.sh` tự đọc file này.
Tài khoản 2 cần thông tin khác thì gán lại biến đó trong `run_day2.sh`, ngay sau dòng `source personal.local.sh`.

## Cài đặt (một lần)

```bash
cd ~/Workspace/atvncg && python3 -m venv .venv && source .venv/bin/activate && pip install playwright
```

Script dùng Google Chrome có sẵn trên máy, không cần `playwright install`.

### Cài trên máy mới (tải từ GitHub về)

Máy mới không có các file trong mục "Những gì KHÔNG có trên GitHub", nên cần làm lại:

1. Tải code về và cài thư viện:
   ```bash
   git clone https://github.com/maipvk/atvncg.git ~/Workspace/atvncg
   ```
   ```bash
   cd ~/Workspace/atvncg && python3 -m venv .venv && source .venv/bin/activate && pip install playwright
   ```
2. Tạo file thông tin cá nhân rồi mở ra điền:
   ```bash
   cp ~/Workspace/atvncg/personal.example.sh ~/Workspace/atvncg/personal.local.sh
   ```
3. Đăng nhập lại từng tài khoản (mục bên dưới).

## Đăng nhập trước (một lần cho mỗi tài khoản)

Chạy `run_day1.sh`, khi Chrome mở và terminal nhắc thì đăng nhập tài khoản 1, bấm Enter, rồi Ctrl+C để dừng.
Làm tương tự với `run_day2.sh` cho tài khoản 2. Phiên đăng nhập được lưu trong `chrome-acc1/`, `chrome-acc2/`.

**Đăng nhập bằng Google?** Google chặn đăng nhập trong cửa sổ do script điều khiển ("Couldn't sign you in").
Khi đó đăng nhập bằng Chrome thường với cùng profile:

```bash
~/Workspace/atvncg/login.sh chrome-acc1
```

Đăng nhập Ticketbox bằng Google trong cửa sổ vừa mở, rồi **Cmd+Q** cửa sổ đó (bắt buộc đóng trước khi chạy script).
Làm lại với `chrome-acc2`.

## Ngày mở bán

### Cách chính: 2 tài khoản song song, dùng chung 1 mã

YFan xác nhận 1 mã presale dùng được cho 2 tài khoản Ticketbox cùng lúc: một tài khoản mua DAY 3, tài khoản kia mua DAY 4
(mỗi ngày 1 đơn). Điền mã vào `CODE` trong `personal.local.sh` (hai file chạy dùng chung), mỗi file chạy **một ngày khác nhau**:

```zsh
# run_day1.sh                          # run_day2.sh
SHOWTIMES=("05 Tháng 12")              SHOWTIMES=("06 Tháng 12")
```

Trước giờ mở bán 5–10 phút, mở 2 tab terminal (Cmd+T), mỗi tab chạy một file:

```bash
~/Workspace/atvncg/run_day1.sh
```

```bash
~/Workspace/atvncg/run_day2.sh
```

Đặt 2 cửa sổ Chrome cạnh nhau. Hai CAPTCHA hiện gần như cùng lúc thì giải cửa sổ của ngày bạn muốn hơn trước.
**Đừng** để hai file cùng một ngày (mỗi ngày mã chỉ dùng được 1 đơn).

### Cách dự phòng: 1 tài khoản mua lần lượt

Ghi nhiều ngày trong `SHOWTIMES` của một file, vd `SHOWTIMES=("05 Tháng 12" "06 Tháng 12")`, và chỉ chạy file đó.
Script mua ngày đầu tới bước nhập thẻ → bạn thanh toán → gõ `tiep` → script mua ngày kế tiếp với cùng mã.

## Diễn biến khi chạy

1. Script đếm ngược, tới giờ tự tải lại trang và bấm "Mua vé ngay" của ngày đầu tiên trong `SHOWTIMES`.
2. Trang mã presale ("Mua vé sớm / Presale đang diễn ra", trước hoặc sau CAPTCHA đều được) → script tự điền `CODE`, bấm Xác nhận / Tiếp tục.
3. CAPTCHA → **bíp**, bạn giải. Script tự đi tiếp, không cần Enter.
   Hai cửa sổ cùng có CAPTCHA thì giải cửa sổ của ngày bạn muốn hơn trước.
4. Hàng chờ (nếu có) → để yên.
5. Sơ đồ "Chọn khu vực" → script bấm zone đầu trong `ZONES`, chỉnh số lượng trong pop-up, bấm "Tiếp tục".
   Mỗi vòng script quét trạng thái các zone trong `ZONES` (theo dữ liệu Ticketbox): zone còn vé thử trước theo thứ tự
   bạn ghi, zone hết vé dồn xuống cuối và chỉ thử nhanh. Hết danh sách thì quay vòng (vé có thể được nhả ra).
   Zone còn ít vé hơn `QTY` thì lấy số còn lại. Sau 3 phút không được → **bíp**, giao lại cho bạn tự bấm.
6. "Bảng câu hỏi" → script tự điền Họ tên / Số điện thoại (kể cả ô "Số điện thoại/Căn cước công dân") / Email,
   tự trả lời mọi câu chọn **bắt buộc** (chọn "đồng ý / xác nhận / đã đọc", checkbox bắt buộc thì tích hết),
   **để trống** các ô xuất hoá đơn không bắt buộc, rồi bấm Tiếp tục.
   Còn câu bắt buộc script không biết trả lời → **bíp** và in danh sách câu còn thiếu; bạn tự điền. Khi **mọi** câu bắt
   buộc đã có trả lời và bạn ngừng gõ 2 giây, script tự bấm Tiếp tục.
7. Trang Thanh toán → script chọn `PAYMENT` (mặc định "Thẻ ghi nợ/Thẻ tín dụng"), tích ô đồng ý điều khoản, bấm "Thanh toán".
   Đợt presale Techcombank: pop-up "Nhập số thẻ để kiểm tra" → script nhập `CARD_BIN` (6 số đầu thẻ), tích ô, bấm Xác nhận.
   `CARD_BIN` để trống ở đợt membership / mở bán thường.
8. **Bíp** → bạn **tự nhập thông tin thẻ** và hoàn tất. Thanh toán xong gõ `xong` + Enter để đóng Chrome.

## Dừng script

Bấm **Ctrl+C một lần** rồi chờ: script dừng ở chỗ an toàn và tự đóng Chrome để giữ phiên đăng nhập.
Bấm Ctrl+C lần 2 là thoát ngay, có thể phải đăng nhập lại bằng `login.sh`.

## Lưu ý

- Mỗi ngày trong `SHOWTIMES` ghi giống hệt dòng trong "Lịch diễn", ngày 2 chữ số: `"01 Tháng 11"`.
- `ZONES` ghi theo tên hạng vé (vd `"Trôi Theo Con Nước (R2)"`) hoặc chữ trên sơ đồ; script bỏ qua hoa/thường, dấu cách, ngoặc
  và dấu tiếng Việt ("Hoả" / "Hỏa" / "Hoa" đều khớp).
  Lúc vào sơ đồ, terminal in ra các chữ đọc được trên sơ đồ (cũng lưu ở `debug/zones_<profile>.json`).
- Ticketbox có thể đổi giao diện: nếu script không nhận ra trang/nút, sửa các hằng `TEXT_*` / `SEL_*` đầu `ticketbox_helper.py`.
- Bật đồng bộ giờ tự động trên máy để `OPEN_AT` chính xác.
- Điều khoản Ticketbox có thể cấm công cụ tự động / nhiều tài khoản; bạn tự chịu rủi ro về tài khoản.
