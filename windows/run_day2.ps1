# Bản Windows của run_day2.sh.
# Tài khoản 2 – chạy SONG SONG với run_day1.ps1, mỗi file 1 ngày khác nhau. Dùng chung 1 mã presale được
# (YFan xác nhận: 1 mã dùng cho 2 tài khoản Ticketbox, 1 tài khoản mua DAY 3, 1 tài khoản mua DAY 4).
# Cấu hình riêng của ngày này (link sự kiện + giờ mở bán chung nằm trong ticketbox_helper.py).
# Cách chạy: powershell -ExecutionPolicy Bypass -File windows\run_day2.ps1
$ProfileDir = ".\chrome-acc2"
# Ngày muốn mua, ghi giống dòng trong "Lịch diễn". Nhiều ngày = mua LẦN LƯỢT trong cùng cửa sổ, cùng mã CODE (trong personal.local.ps1):
# xong đơn ngày đầu (bạn thanh toán) thì gõ 'tiep' để script mua ngày kế tiếp. Ngày quan trọng hơn để trước.
$SHOWTIMES = @("28 Tháng 11")
$ZONES = @("ĐỘC BẢN", "NGÔI SAO 3", "DẤU ẤN 2", "NIÊN THIẾU 2") # @("ĐỈNH NÓC", "SỤC SÔI")      # zone theo thứ tự ưu tiên
$QTY = 1
# Phương thức thanh toán chọn sẵn (ghi giống chữ trên trang Thanh toán). Thông tin thẻ bạn tự nhập.
$PAYMENT = "Thẻ ghi nợ/Thẻ tín dụng"

# Chạy từ thư mục gốc repo: ticketbox_helper.py, .venv, chrome-acc*, debug\ dùng chung với bản macOS
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { Write-Host "Chưa cài .venv – xem mục Cài đặt trong windows\README.md."; exit 1 }
# Họ tên / SĐT / email / mã presale / 6 số đầu thẻ nằm trong windows\personal.local.ps1 (không đẩy lên GitHub)
$Personal = Join-Path $PSScriptRoot "personal.local.ps1"
if (-not (Test-Path $Personal)) { Write-Host "Thiếu windows\personal.local.ps1 – chép windows\personal.example.ps1 thành personal.local.ps1 rồi điền."; exit 1 }
. $Personal

# Dạng --tên=giá-trị: Windows PowerShell bỏ mất tham số chuỗi rỗng, viết liền dấu = thì giá trị "" vẫn tới được Python
$PyArgs = @("windows/ticketbox_windows.py", "--profile=$ProfileDir", "--qty=$QTY", "--code=$CODE",
            "--fullname=$FULLNAME", "--phone=$PHONE", "--email=$EMAIL", "--payment=$PAYMENT",
            "--card-bin=$CARD_BIN")
foreach ($d in $SHOWTIMES) { $PyArgs += "--showtime=$d" }
foreach ($z in $ZONES) { $PyArgs += "--zone=$z" }
$env:PYTHONUTF8 = "1"
& $Python @PyArgs
