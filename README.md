# Quản lý kho CLI

Công cụ tự động giúp xuất hóa đơn trong Misa

Hướng dẫn sử dụng
- Chạy chế độ tự động:
  - Script: `WarehouseExport.exe -a . -s 0`
  - Note: hệ thống sẽ tự động lấy hóa đơn từ Sapo chạy từ 17:00 hôm trước đến 16h59 hiện tại  
- Chạy chế độ thủ công theo ngày:
  - Script: `WarehouseExport.exe -d . -s 0`
  - Hệ thống yêu cầu nhập ngày bắt đầu và kết thúc

- Thứ tự Shop:
  - QuocCoQuocNghiepShop : `0`
  - ThaoDuocGiang : `1`

- Ý nghĩa viết tắt từ khóa
  - `-a:` auto
  - `-s:` shop
  - `-d:` day