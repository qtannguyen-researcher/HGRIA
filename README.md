# HGRIA - Hand Gesture Recognition for Interactive Applications

A real-time hand gesture recognition system using MediaPipe for gesture detection, Flask-SocketIO for WebSocket communication, and a browser-based HTML5 Canvas game as the frontend.

## Features

- **9 Built-in Gestures**: Open Palm, Closed Fist, Point Left/Right, Thumb Up, Victory, Stop, Pinch, OK
- **Real-time Processing**: Sub-150ms end-to-end latency
- **Rule-based Classification**: No training data required
- **WebSocket Communication**: Flask-SocketIO for bidirectional events
- **Google Colab Support**: Webcam bridge via JavaScript
- **Keyboard Fallback**: Arrow keys, Space, P, S for testing without camera

## Prerequisites

- Python 3.8+
- Webcam (optional, keyboard fallback available)
- Google Colab (for cloud deployment)

## Quick Start

### 1. Install Dependencies

```bash
cd /home/qtannguyen/projects/researcher/HGRIA
pip install -r requirements.txt
```

### 2. Configure Camera (Optional)

Edit `config/config.json` to match your setup:

```json
{
    "camera": {
        "index": 0,           // Camera device index
        "frame_width": 640,   // Frame width
        "frame_height": 480,  // Frame height
        "target_fps": 30,    // Target FPS
        "colab_mode": false   // Set to true for Google Colab
    }
}
```

### 3. Run the Server

```bash
# From project root
python -m backend.main
```

Or:

```bash
cd backend
python main.py
```

Expected output:

```
Server running at: http://0.0.0.0:5000
```

### 4. Open the Frontend

Open `frontend/index.html` in your browser, or visit:

```
http://localhost:5000
```

## Triển khai trên Colab + ngrok

### Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────────┐
│                    ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Browser (Frontend)     ngrok Tunnel      Colab Backend   │
│   ┌──────────────┐      ┌──────────┐     ┌──────────────┐   │
│   │  GitHub Pages │ ←─── │  HTTPS   │ ←── │  Flask +     │   │
│   │  / Vercel    │      │  Tunnel  │     │  MediaPipe   │   │
│   └──────────────┘      └──────────┘     └──────────────┘   │
│         │                                          │        │
│         │           Google Drive                    │        │
│         └──────────────┬───────────────────────────┘        │
│                        │ logs/                             │
└─────────────────────────────────────────────────────────────┘
```

### Điều kiện tiên quyết

- Tài khoản Google (để sử dụng Google Colab)
- Tài khoản ngrok miễn phí (đăng ký tại https://dashboard.ngrok.com)
- Trình duyệt hỗ trợ WebRTC (Chrome, Edge, Firefox)

### Các bước triển khai

**1. Chuẩn bị Google Drive**

- Tải toàn bộ project HGRIA lên Google Drive tại đường dẫn: `/content/drive/MyDrive/HGRIA/`
- Đảm bảo có file `requirements.txt` trong thư mục gốc

**2. Mở Notebook Colab**

- Mở file `notebooks/HGRIA_Launch.ipynb` trong Google Colab
- Kết nối Google Drive (ô 1)

**3. Cài đặt phụ thuộc**

- Chạy ô 2 để copy project và cài dependencies
- Kiểm tra các package đã cài đặt thành công

**4. Cấu hình ngrok**

- Chạy ô 3
- Nhập ngrok authtoken (khuyến nghị) hoặc bỏ trống để sử dụng anonymous tunnel
- Anonymous tunnel có thể bị ngắt kết nối thường xuyên

**5. Khởi động Backend**

- Chạy ô 4 để khởi tạo ngrok tunnel và lấy URL
- Chạy ô 5 để cấu hình Colab mode
- Chạy ô 6 (blocking) để khởi động server

**6. Truy cập Frontend**

- Mở trình duyệt và truy cập: `https://your-username.github.io/HGRIA/?server=<NGROK_URL>`
- Hoặc nhập Ngrok URL vào form setup trên trang frontend
- Cho phép truy cập webcam khi được yêu cầu

### Deploy Frontend lên GitHub Pages

Frontend được tự động deploy khi có thay đổi trong thư mục `frontend/`:

```bash
# Frontend sẽ được deploy tự động qua GitHub Actions
# Xem workflow tại: .github/workflows/deploy.yml
```

Hoặc deploy thủ công qua Vercel:

```bash
# Cài Vercel CLI
npm i -g vercel

# Deploy
vercel
```

## Google Colab Deployment

### 1. Upload Files to Colab

Upload the entire project folder to Google Drive.

### 2. Update Configuration

Set `colab_mode` to `true` in `config/config.json`:

```python
# In your notebook
config = ConfigurationManager('config/config.json')
config._data['camera']['colab_mode'] = True
```

### 3. Start ngrok Tunnel

```python
from pyngrok import ngrok

tunnel = ngrok.connect(5000, 'http')
public_url = tunnel.public_url.replace('http://', 'https://')
print(f'Public URL: {public_url}')
```

### 4. Start Webcam Bridge

The notebook cell will capture webcam frames and POST them to the server.

### 5. Open Public URL in Browser

Use the ngrok URL from step 3.

## Keyboard Controls

When no camera is available, use these keyboard shortcuts:

| Key | Gesture |
|-----|---------|
| Arrow Left | Point Left |
| Arrow Right | Point Right |
| Space | Thumb Up (Jump) |
| P | Stop (Pause) |
| S | Closed Fist (Speed Boost) |
| Enter | OK (Confirm) |
| Escape | Victory (Select) |
| +/= | Pinch (Zoom In) |

## Configuration

All settings are in `config/config.json`:

### Camera Settings

```json
"camera": {
    "index": 0,
    "frame_width": 640,
    "frame_height": 480,
    "target_fps": 30,
    "colab_mode": false
}
```

### MediaPipe Settings

```json
"mediapipe": {
    "min_detection_confidence": 0.7,
    "min_tracking_confidence": 0.5,
    "max_num_hands": 1,
    "model_complexity": 0
}
```

### Gesture Recognition

```json
"gesture_recognition": {
    "confidence_threshold": 0.75,
    "smoothing_window_size": 5,
    "noise_filter_blur_threshold": 100,
    "dominant_hand": "Right"
}
```

### Per-Gesture Cooldowns (ms)

```json
"gesture_cooldowns_ms": {
    "open_palm": 500,
    "closed_fist": 500,
    "point_left": 300,
    "point_right": 300,
    "thumb_up": 500,
    "victory": 500,
    "stop": 1000,
    "pinch": 400,
    "ok": 500
}
```

### Hot-Reloadable Fields

These fields can be updated at runtime via the API:

- `gesture_recognition.confidence_threshold`
- `gesture_recognition.smoothing_window_size`
- `logging.level`
- `debug.debug_mode`
- `gesture_cooldowns_ms.*`

## API Endpoints

### GET /health

Health check endpoint.

```bash
curl http://localhost:5000/health
```

Response:
```json
{
    "status": "ok",
    "version": "1.0.0",
    "pipeline_state": "Idle"
}
```

### GET /api/config

Get current configuration.

```bash
curl http://localhost:5000/api/config
```

### PUT /api/config

Update hot-reloadable configuration fields.

```bash
curl -X PUT http://localhost:5000/api/config \
    -H "Content-Type: application/json" \
    -d '{"gesture_recognition.confidence_threshold": 0.85}'
```

Response:
```json
{
    "updated": ["gesture_recognition.confidence_threshold"],
    "rejected": []
}
```

### GET /api/session

Get session statistics.

```bash
curl http://localhost:5000/api/session
```

Response:
```json
{
    "session_id": "uuid-here",
    "commands_sent": 42,
    "gesture_counts": {"thumb_up": 15, "point_left": 27},
    "avg_latency_ms": 45.2
}
```

### DELETE /api/session

Reset session counters.

```bash
curl -X DELETE http://localhost:5000/api/session
```

### POST /api/frame (Colab Mode)

Receive base64 JPEG frame from browser.

```python
import base64
import requests

with open('frame.jpg', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
requests.post('http://localhost:5000/api/frame', json={'image': b64})
```

## WebSocket Events

### Client → Server

| Event | Payload | Description |
|-------|---------|-------------|
| `client_ready` | `{client_id, user_agent}` | Client initialization |
| `pause_pipeline` | - | Pause gesture detection |
| `resume_pipeline` | - | Resume gesture detection |
| `ping` | `{timestamp}` | Latency measurement |

### Server → Client

| Event | Payload | Description |
|-------|---------|-------------|
| `server_info` | `{session_id, version, config}` | Server info on connect |
| `gesture_command` | `{command_id, gesture_name, command_type, ...}` | Gesture command |
| `gesture_update` | `{gesture_name, confidence}` | Real-time gesture display |
| `system_state_change` | `{old_state, new_state}` | State machine transition |
| `system_error` | `{error_code, message, recoverable}` | Error notification |
| `server_shutdown` | `{reason}` | Server shutdown |
| `pong` | `{timestamp}` | Ping response |

## Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=backend --cov-report=html

# Run specific test file
pytest tests/test_classifier.py -v

# Run with hypothesis (property-based tests)
pytest tests/ -hypothesis-show-statistics
```

## Project Structure

```
HGRIA/
├── backend/
│   ├── core/
│   │   ├── models.py          # Data models
│   │   ├── errors.py         # Exception hierarchy
│   │   ├── configuration.py  # Configuration manager
│   │   └── state_manager.py  # FSM implementation
│   ├── pipeline/
│   │   ├── camera.py         # Camera capture
│   │   ├── preprocessor.py   # Frame preprocessing
│   │   ├── detector.py       # MediaPipe hand detection
│   │   ├── extractor.py      # Landmark extraction
│   │   ├── classifier.py     # Gesture classification
│   │   ├── filter.py         # Noise & temporal filters
│   │   ├── cooldown.py       # Cooldown manager
│   │   ├── commander.py       # Command generation
│   │   └── pipeline_runner.py # Pipeline orchestration
│   ├── routes/
│   │   ├── health.py         # GET /health
│   │   ├── config_api.py     # GET/PUT /api/config
│   │   └── session.py        # GET/DELETE /api/session
│   ├── websocket/
│   │   └── handlers.py       # SocketIO handlers
│   ├── utils/
│   │   ├── logger.py         # Structured JSON logger
│   │   └── geometry.py       # Geometric helpers
│   ├── app.py                # Flask application factory
│   └── main.py               # System orchestrator
├── frontend/
│   ├── index.html            # Main HTML
│   ├── css/
│   │   ├── main.css         # Layout styles
│   │   ├── game.css         # Canvas styles
│   │   └── hud.css          # HUD overlay styles
│   ├── js/
│   │   ├── config.js        # Configuration
│   │   ├── state.js         # Game state
│   │   ├── websocket.js     # Socket.IO client
│   │   ├── audio.js         # Web Audio API
│   │   ├── renderer.js      # Canvas rendering
│   │   ├── game.js          # Game engine
│   │   ├── hud.js           # HUD manager
│   │   └── main.js          # Bootstrap
│   └── assets/
│       ├── gestures/        # Gesture reference images
│       └── sounds/          # Sound effects
├── config/
│   └── config.json          # Default configuration
├── notebooks/
│   └── HGRIA_Launch.ipynb # Colab launch notebook
├── tests/
│   ├── fixtures.py          # Test fixtures
│   ├── test_classifier.py   # Classifier tests
│   ├── test_filter.py       # Filter tests
│   ├── test_cooldown.py     # Cooldown tests
│   ├── test_commander.py    # Commander tests
│   ├── test_configuration.py # Config tests
│   ├── test_state_manager.py # State manager tests
│   ├── conftest.py          # Pytest fixtures
│   ├── test_flask_api.py    # HTTP API tests
│   └── test_websocket.py    # WebSocket tests
├── requirements.txt          # Python dependencies
├── .gitignore
└── README.md                 # This file
```

## Troubleshooting

### Colab + ngrok Issues

| Vấn đề | Giải pháp |
|---------|-----------|
| Colab session timeout | Re-run ô 6 (server sẽ tự khởi động lại) |
| ngrok URL thay đổi | Re-run ô 4, 5, 6 và cập nhật URL mới vào Frontend |
| Webcam bị từ chối | Sử dụng keyboard fallback (Arrow keys, Space, P, S) |
| Anonymous tunnel bị ngắt | Đăng ký ngrok và nhập authtoken ở ô 3 |
| Kết nối WebSocket thất bại | Kiểm tra Ngrok URL, đảm bảo Backend đang chạy |

### Camera Not Detected

```bash
# List available cameras
python -c "import cv2; cap = cv2.VideoCapture(0); print('Camera OK' if cap.isOpened() else 'No camera')"

# Try different camera index
# Edit config.json: "camera": {"index": 1}
```

### Port Already in Use

```bash
# Find process using port 5000
lsof -i :5000

# Kill the process
kill -9 <PID>

# Or change port in config.json
# "server": {"port": 5001}
```

### MediaPipe Errors

```bash
# Reinstall MediaPipe
pip uninstall mediapipe
pip install mediapipe==0.10.14
```

### WebSocket Connection Issues

1. Check browser console for errors
2. Verify CORS settings in `config.json`
3. Try refreshing the page
4. Check if server is running

### High Latency

1. Reduce `smoothing_window_size` to 3
2. Set `model_complexity` to 0
3. Reduce camera resolution
4. Check network connection (for Colab)

## Development

### Adding Custom Gestures

1. Add rule definition to `config.json`:

```json
"custom_gestures": [
    {
        "name": "my_gesture",
        "confidence_threshold": 0.80,
        "cooldown_ms": 500,
        "command_type": "ACTION",
        "command_value": {"action": "custom"},
        "rules": [
            {"type": "finger_extended", "parameters": {"tip": 8, "pip": 6}}
        ]
    }
]
```

2. Add command mapping in `backend/pipeline/commander.py`:

```python
COMMAND_MAP["my_gesture"] = {"command_type": "ACTION", "command_value": {"action": "custom"}}
```

### Adding Custom Rules

Add new rule type in `backend/pipeline/classifier.py`:

```python
elif self.rule_type == "my_custom_rule":
    # Implement rule logic
    return min(max(value, 0.0), 1.0)
```

## License

MIT License
