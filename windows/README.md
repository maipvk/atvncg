# Ticketbox helper – chạy trên Windows

Thư mục `windows\` là bản Windows của các file `.sh` (macOS) ở thư mục gốc. Cách chạy và diễn biến giống hệt bản macOS
(xem [README.md](../README.md)); file này chỉ ghi những chỗ khác.

## Phân chia file

| macOS (thư mục gốc) | Windows (`windows\`) |
|---|---|
| `login.sh` | `login.ps1` |
| `run_day1.sh` | `run_day1.ps1` |
| `run_day2.sh` | `run_day2.ps1` |
| `personal.example.sh` → `personal.local.sh` | `personal.example.ps1` → `personal.local.ps1` |
| `ticketbox_helper.py` | `ticketbox_windows.py` (chạy `ticketbox_helper.py` + các chỗ sửa riêng cho Windows) |

Dùng chung cho cả hai: `ticketbox_helper.py`, `.venv\`, `chrome-acc1\`, `chrome-acc2\`, `debug\` (đều ở thư mục gốc).
Sửa riêng cho Windows thì sửa `ticketbox_windows.py`, **không** sửa `ticketbox_helper.py` (đang chạy tốt trên macOS).
Muốn đổi zone / ngày / số lượng trên Windows thì sửa file `.ps1`, **không** sửa file `.sh` (và ngược lại).

## Cài đặt (một lần)

Cần Python 3 và Google Chrome. Cài Python bằng lệnh dưới (hoặc tải ở python.org, tích "Add python.exe to PATH"),
cài xong thì **đóng và mở lại** cửa sổ PowerShell để nhận lệnh `python`:

```powershell
winget install -e --id Python.Python.3.12
```

```powershell
git clone https://github.com/maipvk/atvncg.git $HOME\atvncg
```
```powershell
cd $HOME\atvncg; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install playwright
```
```powershell
copy windows\personal.example.ps1 windows\personal.local.ps1
```

Mở `windows\personal.local.ps1` rồi điền họ tên, SĐT, email, mã presale, 6 số đầu thẻ.
Lưu file dạng **UTF-8 with BOM** nếu có chữ tiếng Việt (Notepad: File → Save as → Encoding), nếu không Windows PowerShell đọc sai dấu.

## Chạy

Windows mặc định chặn chạy file `.ps1`, nên luôn chạy kèm `-ExecutionPolicy Bypass` (chỉ áp dụng cho lần chạy đó):

```powershell
cd $HOME\atvncg; powershell -ExecutionPolicy Bypass -File windows\run_day1.ps1
```

Chạy song song 2 tài khoản: mở 2 cửa sổ PowerShell, một cửa sổ chạy `run_day1.ps1`, cửa sổ kia chạy `run_day2.ps1`.

Đăng nhập bằng Google (Google chặn đăng nhập trong Chrome do script điều khiển):

```powershell
cd $HOME\atvncg; powershell -ExecutionPolicy Bypass -File windows\login.ps1 chrome-acc1
```

Đăng nhập xong thì **đóng hẳn** cửa sổ Chrome đó (thay cho Cmd+Q trên macOS) trước khi chạy `run_day1.ps1`.

## Khác với macOS

- Lúc kiểm tra đăng nhập (vài giây đầu), cửa sổ Chrome tự phóng to rồi trở lại kích thước cũ. Lý do: cửa sổ hẹp thì
  Ticketbox chỉ hiện ảnh đại diện thay cho chữ "Tài khoản", script gốc sẽ báo nhầm "Bạn chưa đăng nhập".

- **Gõ `huy` + Enter để dừng canh vé KHÔNG hoạt động trên Windows** (Python trên Windows không đọc bàn phím kiểu này được).
  Muốn dừng sớm thì bấm **Ctrl+C một lần** rồi chờ script đóng Chrome. `tiep` và `xong` vẫn dùng bình thường.
- Profile Chrome tạo trên Windows chỉ dùng được trên Windows (cookie được mã hoá theo máy); đừng chép `chrome-acc*` giữa macOS và Windows.
