# HGRIA — Local Launch Guide

Hướng dẫn chạy HGRIA trên máy local qua notebook `HGRIA_Local.ipynb`.

## Kiến trúc (Local)

```
┌─────────────────────────────────────────────────────────────┐
│                    ARCHITECTURE (LOCAL)                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Browser (Frontend)     ngrok Tunnel      Local Backend   │
│   ┌──────────────┐      ┌──────────┐     ┌──────────────┐   │
│   │  GitHub Pages │ ←─── │  HTTPS   │ ←── │  Flask +     │   │
│   │  / Vercel    │      │  Tunnel  │     │  MediaPipe   │   │
│   └──────────────┘      └──────────┘     └──────────────┘   │
│                                                 │           │
│                                            <project>/logs/  │
└─────────────────────────────────────────────────────────────┘
```

Frontend được host tĩnh (GitHub Pages hoặc Vercel). Backend chạy local và được expose qua ngrok HTTPS tunnel. Webcam frames đi từ trình duyệt → tunnel → Flask, gesture commands trả về theo chiều ngược lại qua WebSocket.

---

## Điều kiện tiên quyết

| Yêu cầu | Ghi chú |
|---------|---------|
| Python 3.10+ | Khuyến nghị dùng virtualenv hoặc conda |
| pip | Đi kèm Python |
| Tài khoản ngrok | Free tier hoạt động — [đăng ký tại đây](https://dashboard.ngrok.com/signup) |
| Trình duyệt WebRTC | Chrome, Edge hoặc Firefox |

---

## Cài đặt

```bash
# Clone hoặc mở project
cd <project_root>

# Cài toàn bộ dependencies
pip install -r requirements.txt
```

---

## Chạy notebook từng bước

Mở `notebooks/HGRIA_Local.ipynb` và chạy tuần tự từng ô.

### Ô 1 — Verify dependencies

Kiểm tra NumPy, Protobuf, MediaPipe, TensorFlow đã cài đúng version.

```
NumPy: x.x.x
MediaPipe: x.x.x
TensorFlow: x.x.x
MediaPipe OK
TensorFlow OK
```

Nếu có lỗi import, chạy lại `pip install -r requirements.txt`.

### Ô 2 — Set up project root

Tự động detect `PROJECT_ROOT` (đi lên một cấp từ thư mục `notebooks/`) và thêm vào `sys.path`. Không cần chỉnh sửa.

### Ô 3 — Cấu hình ngrok authtoken

Dán authtoken từ [dashboard.ngrok.com](https://dashboard.ngrok.com/get-started/your-authtoken) vào biến `NGROK_AUTHTOKEN`:

```python
NGROK_AUTHTOKEN = "your_token_here"
```

- Để trống → dùng anonymous tunnel (có thể ngắt sau ~2 giờ).
- Token không đúng định dạng (< 20 ký tự, ký tự lạ) → ô sẽ raise `ValueError`.

### Ô 4 — Patch config cho môi trường local

Tự động ghi đè các trường sau trong `config/config.json`:

| Trường | Giá trị được set |
|--------|-----------------|
| `camera.colab_mode` | `false` |
| `server.cors_origins` | `"*"` |
| `logging.log_to_file` | `true` |
| `logging.log_file_path` | `<project_root>/logs/` |

Thư mục `logs/` được tạo tự động nếu chưa tồn tại.

> **Lưu ý:** Ô này ghi đè trực tiếp `config.json`. Nếu bạn đang chỉnh config thủ công, hãy backup trước.

### Ô 5 — Apply in-place patches và clear module cache

Ô này làm hai việc:

1. **Patch `backend/core/configuration.py`** — sửa `__getattr__` để `gesture_cooldowns_ms` và `custom_gestures` trả về `dict` thay vì `_Namespace` (tránh lỗi `.get()` không tìm thấy). Nếu file đã có fix này thì bỏ qua.

2. **Evict module cache** — xóa tất cả module `backend.*` khỏi `sys.modules` để lần import tiếp theo luôn đọc source mới nhất thay vì bytecode cũ.

Output mong đợi:
```
✓ Patched configuration.py
✓ Evicted N cached module(s) — fresh import guaranteed
```
hoặc:
```
✓ configuration.py already contains the fix — no patch needed
```

### Ô 6 — Start the HGRIA Server (blocking)

Khởi động `SystemOrchestrator`. Khi server sẵn sàng sẽ in ra:

```
Server URL : http://0.0.0.0:5000
Public URL : https://xxxx.ngrok-free.app
Frontend   : https://qtannguyen-researcher.github.io/HGRIA/?server=https://xxxx.ngrok-free.app
```

**Copy dòng `Frontend :` và mở trong trình duyệt.**

Ô này chạy blocking (server giữ kernel). Để dừng: nhấn nút Stop (■) hoặc **Kernel → Interrupt**.

---

## Sau khi server khởi động

1. Mở URL `Frontend :` trong trình duyệt.
2. Cho phép truy cập webcam khi được hỏi.
3. Bắt đầu nhận diện cử chỉ.

Nếu không có webcam, dùng keyboard fallback:

| Phím | Hành động |
|------|-----------|
| Arrow Left / Right | Di chuyển trái / phải |
| Space | Nhảy (Thumb Up) |
| P | Tạm dừng |
| S | Tăng tốc (Speed Boost) |
| Enter | Xác nhận |

---

## Xử lý sự cố

| Vấn đề | Giải pháp |
|--------|-----------|
| ngrok URL thay đổi | Dừng ô 6, chạy lại ô 4 và 6, dùng URL mới |
| `authtoken does not look valid` | Kiểm tra lại token trong ô 3, lấy từ dashboard ngrok |
| Code thay đổi không có hiệu lực | Chạy lại ô 5 (evict cache) rồi ô 6 |
| Webcam bị từ chối | Dùng keyboard fallback (bảng trên) |
| Port 5000 đang bị chiếm | `lsof -ti:5000 \| xargs kill` rồi chạy lại ô 6 |
| Import error `backend.*` | Kiểm tra `PROJECT_ROOT` ở ô 2, đảm bảo `sys.path` đúng |
| `onnxruntime` không tìm thấy | `pip install onnxruntime==1.13.1` |

---

## Logs

Server ghi log ra `<project_root>/logs/`. Kiểm tra file log mới nhất để debug:

```bash
ls -lt logs/
```
