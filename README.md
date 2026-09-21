# 🎬 Batch Video Downloader Web App

Ứng dụng web tải video đơn giản, hiện đại và tiện lợi được xây dựng trên nền tảng **yt-dlp** và **Flask**.

## ✨ Tính năng nổi bật
- **Dán nhiều URL cùng lúc (Multiline Input)**: Hỗ trợ dán nhiều đường link video (mỗi dòng một link) trực tiếp từ clipboard.
- **Hàng đợi tải tuần tự (Sequential Queue)**: Tự động xếp hàng các video và tải lần lượt từng video một (`Queue Worker`), tránh nghẽn mạng hay quá tải máy tính.
- **Theo dõi tiến độ chi tiết**: Hiển thị trạng thái của từng video trong hàng đợi (`Chờ lượt`, `Đang tải X%`, `Đang ghép file ffmpeg`, `Hoàn thành`, `Lỗi`).
- **Tùy chọn định dạng linh hoạt**:
  - 👑 **Video Tốt Nhất**: Tự động chọn độ phân giải cao nhất (MP4).
  - 📺 **Full HD (1080p)**
  - 📱 **HD (720p)**
  - 🎵 **Chỉ Nhạc (MP3 192kbps)**
- **Quản lý file & Mở nhanh thư mục**: Nút mở trực tiếp thư mục `downloads` trên Windows Explorer và nút tải file về máy.
- **Hỗ trợ 1000+ trang web**: YouTube, TikTok, Facebook, Instagram (Reels), X (Twitter), SoundCloud, Bilibili,...

---

## 🚀 Hướng dẫn khởi động

### Cách 1: Chạy nhanh trên Windows bằng `run.bat` (Khuyên dùng)
1. Nhấp đúp chuột vào file `run.bat`.
2. Trình duyệt web sẽ tự động mở trang: `http://localhost:5000`.

---

### Cách 2: Chạy bằng dòng lệnh (Terminal / PowerShell)
1. Cài đặt các thư viện (nếu chưa có):
   ```bash
   pip install -r requirements.txt
   ```
2. Khởi động ứng dụng:
   ```bash
   python app.py
   ```
3. Mở trình duyệt và truy cập: [http://localhost:5000](http://localhost:5000)

---

## 📋 Cách sử dụng tải hàng loạt
1. Sao chép danh sách các đường link video (ví dụ từ file txt, note hoặc trình duyệt).
2. Nhấn nút **"Dán"** hoặc dán trực tiếp vào ô nhập (mỗi dòng một đường link).
3. Chọn chất lượng mong muốn (Video tốt nhất, 1080p, 720p, hoặc MP3).
4. Nhấn **"Thêm Vào Hàng Đợi & Tải Ngay"**.
5. Hệ thống sẽ tự động tải lần lượt từng video cho đến khi hoàn tất!
