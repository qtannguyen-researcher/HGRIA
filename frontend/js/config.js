/**
 * HGRIA Frontend Configuration
 * Contains constants, default values, and gesture guide mappings
 */

// ===== Server Configuration =====
const CONFIG = {
    // Server URL - overridable via multiple sources in priority order
    get SERVER_URL() {
        // 1. window.HGRIA_BACKEND_URL (set by Colab notebook)
        if (window.HGRIA_BACKEND_URL) {
            return window.HGRIA_BACKEND_URL;
        }
        // 2. localStorage
        const stored = localStorage.getItem('hgria_backend_url');
        if (stored) {
            return stored;
        }
        // 3. query param ?server=
        const params = new URLSearchParams(window.location.search);
        const serverParam = params.get('server');
        if (serverParam) {
            return serverParam;
        }
        // 4. Default to localhost
        return 'http://localhost:5000';
    },
    
    // Connection settings
    DEFAULT_TARGET_FPS: 30,
    MAX_RETRY_COUNT: 10,
    PING_INTERVAL_MS: 2000,
    
    // Backoff intervals for reconnection (ms)
    BACKOFF_MS: [1000, 2000, 4000, 8000, 16000],
    
    // Command queue
    MAX_COMMAND_QUEUE: 10,
};

// ===== Gesture Guide Map =====
const GESTURE_GUIDE = {
    'open_palm': {
        name: 'Open Palm',
        description: 'Stop/Brake',
        icon: 'assets/gestures/open_palm.png',
        command: 'stop',
    },
    'closed_fist': {
        name: 'Closed Fist',
        description: 'Speed Boost',
        icon: 'assets/gestures/closed_fist.png',
        command: 'speed_boost',
    },
    'point_left': {
        name: 'Point Left',
        description: 'Move Left',
        icon: 'assets/gestures/point_left.png',
        command: 'left',
    },
    'point_right': {
        name: 'Point Right',
        description: 'Move Right',
        icon: 'assets/gestures/point_right.png',
        command: 'right',
    },
    'thumb_up': {
        name: 'Thumb Up',
        description: 'Jump',
        icon: 'assets/gestures/thumb_up.png',
        command: 'jump',
    },
    'victory': {
        name: 'Victory',
        description: 'Select',
        icon: 'assets/gestures/victory.png',
        command: 'select',
    },
    'stop': {
        name: 'Stop',
        description: 'Pause',
        icon: 'assets/gestures/stop.png',
        command: 'pause',
    },
    'pinch': {
        name: 'Pinch',
        description: 'Zoom In',
        icon: 'assets/gestures/pinch.png',
        command: 'zoom_in',
    },
    'ok': {
        name: 'OK',
        description: 'Confirm',
        icon: 'assets/gestures/ok.png',
        command: 'confirm',
    },
};

// ===== Valid Gesture Names =====
const VALID_GESTURE_NAMES = Object.keys(GESTURE_GUIDE);

// ===== Safe Gesture Name Regex =====
const SAFE_GESTURE_RE = /^[a-z0-9_-]{1,32}$/;

/**
 * Validate and sanitize a gesture name
 * @param {string} name - The gesture name to validate
 * @returns {string} - The validated gesture name or 'unknown'
 */
function safeGestureName(name) {
    if (typeof name !== 'string') return 'unknown';
    return SAFE_GESTURE_RE.test(name) ? name : 'unknown';
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { CONFIG, GESTURE_GUIDE, VALID_GESTURE_NAMES, SAFE_GESTURE_RE, safeGestureName };
}
