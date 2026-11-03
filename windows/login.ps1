# Bản Windows của login.sh.
# Mở Chrome BÌNH THƯỜNG (không bị script điều khiển) với profile của một tài khoản để đăng nhập Ticketbox.
# Dùng khi đăng nhập bằng Google: Google chặn đăng nhập trong cửa sổ Chrome do script điều khiển.
# Cách dùng: powershell -ExecutionPolicy Bypass -File windows\login.ps1 chrome-acc1
#   (đăng nhập xong thì ĐÓNG HẲN cửa sổ Chrome đó, rồi mới chạy run_dayX.ps1)
param([Parameter(Mandatory = $true, HelpMessage = "Tên profile, vd chrome-acc1")][string]$ProfileName)

# Profile nằm ở thư mục gốc repo (dùng chung với ticketbox_helper.py), không nằm trong windows\
$Root = Split-Path -Parent $PSScriptRoot

$Chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Chrome) { Write-Host "Không tìm thấy Google Chrome. Cài Chrome trước."; exit 1 }

Start-Process -FilePath $Chrome -ArgumentList "--user-data-dir=`"$Root\$ProfileName`"", "https://ticketbox.vn/"
