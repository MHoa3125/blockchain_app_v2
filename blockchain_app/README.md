# Hệ thống Truy xuất Nguồn gốc Cà phê bằng Blockchain

Một website về hệ thống truy xuất nguồn gốc chuỗi cung ứng cà phê Arabica Cầu Đất dựa trên Công nghệ Blockchain.

---

## Tính năng chính
-Truy xuất nguồn gốc: Cho phép người tiêu dùng tra cứu toàn bộ lịch sử sản phẩm.
-Ghi nhận chuỗi cung ứng: Các đối tác (từ Nông hộ đến Bán lẻ) ghi lại dữ liệu ở mỗi giai đoạn.
-Xác thực dữ liệu: Tự động kiểm tra và đảm bảo tính hợp lệ của thông tin đầu vào.
-Quản trị hệ thống: Admin quản trị hệ thống, phân quyền tài khoản, kiểm tra tính toàn vẹn của Blockchain và reset chuỗi khi cần thiết.
-Bảo mật Blockchain: Dữ liệu được lưu trữ an toàn, minh bạch và không thể thay đổi.

## Công nghệ sử dụng

- **Backend**: Python, Flask
- **Blockchain**: Logic Blockchain được tự triển khai bằng Python (SHA-256 hashing).
- **Database**: MongoDB
- **Frontend**: HTML, Bootstrap
- **APIs**: OCR.space , API Google Sheet 
- **Dependencies**: Xem chi tiết trong `requirements.txt`.

## Cấu hình cài đặt

1.  **Clone repository.**

2.  **Thiết lập MongoDB và lấy chuỗi kết nối.**

3.  **Tạo file `credentials.json`** trong thư mục `blockchain_app` với nội dung:
    ```json
    {
        "MONGO_URI": "your_mongodb_connection_string",
        "OCR_API_KEY": "your_ocr_space_api_key"
    }
    ```

4.  **Cài đặt thư viện và chạy:**
    ```bash
    # (Tùy chọn) Tạo và kích hoạt môi trường ảo
    python -m venv venv
    .\venv\Scripts\activate

    # Cài đặt
    pip install -r requirements.txt

    # Chạy ứng dụng
    flask run
    ```

5.  **Truy cập `http://127.0.0.1:5000` trên trình duyệt.**

## Tài khoản Demo

| Vai trò | Tên đăng nhập | Mật khẩu |
| :--- | :--- | :--- |
| Nông hộ | `nongho` | `nongho123` |
| Đơn vị sơ chế | `soche` | `soche123` |
| Nhà rang xay | `rangxay` | `rangxay123` |
| Nhà phân phối | `nhaphanphoi` | `nhaphanphoi123` |
| Nhà bán lẻ | `banle` | `banle123` |
| Người tiêu dùng | `consumer` | `cons123` |
| Quản trị viên | `admin` | `admin123` |
