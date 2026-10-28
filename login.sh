#!/bin/zsh
# Mở Chrome BÌNH THƯỜNG (không bị script điều khiển) với profile của một tài khoản để đăng nhập Ticketbox.
# Dùng khi đăng nhập bằng Google: Google chặn đăng nhập trong cửa sổ Chrome do script điều khiển.
# Cách dùng: ./login.sh chrome-acc1   (đăng nhập xong thì Cmd+Q cửa sổ đó, rồi mới chạy run_dayX.sh)
PROFILE="${1:?Thiếu tên profile, vd: ./login.sh chrome-acc1}"
cd "$(dirname "$0")"
open -na "Google Chrome" --args --user-data-dir="$PWD/$PROFILE" "https://ticketbox.vn/"
