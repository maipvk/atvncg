# Bản Windows của personal.example.sh.
# Thông tin cá nhân – chép file này thành windows\personal.local.ps1 rồi điền. personal.local.ps1 KHÔNG được đẩy lên GitHub.
# run_day1.ps1 và run_day2.ps1 đều đọc file này. Tài khoản 2 cần thông tin khác thì gán lại biến đó trong run_day2.ps1,
# ngay sau dòng ". $Personal".

# Thông tin người mua để điền "Bảng câu hỏi" (ô CCCD dùng chung với số điện thoại thì luôn điền số điện thoại)
$FULLNAME = ""
$PHONE = ""
$EMAIL = ""

# Mã presale / early bird ("" nếu không có). 1 mã dùng được cho 2 tài khoản, mỗi tài khoản một ngày.
$CODE = ""

# Chỉ cho đợt presale Techcombank: 6 số đầu thẻ cho pop-up "Nhập số thẻ để kiểm tra". "" ở các đợt khác.
$CARD_BIN = ""
