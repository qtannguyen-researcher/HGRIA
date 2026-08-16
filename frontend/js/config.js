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
        // 2. query param ?server=
        const params = new URLSearchParams(window.location.search);
        const serverParam = params.get('server');
        if (serverParam) {
            return serverParam;
        }
        // 3. localStorage
        const stored = localStorage.getItem('hgria_backend_url');
        if (stored) {
            return stored;
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
    // ── Static gestures ──────────────────────────────────────────────────
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

    // ── Dynamic gestures ─────────────────────────────────────────────────
    'SWIPE_LEFT':      { name: 'Swipe Left',       description: 'Move Left',       command: 'left' },
    'SWIPE_RIGHT':     { name: 'Swipe Right',      description: 'Move Right',      command: 'right' },
    'SWIPE_UP':        { name: 'Swipe Up',         description: 'Move Up',         command: 'up' },
    'SWIPE_DOWN':      { name: 'Swipe Down',       description: 'Move Down',       command: 'down' },
    'SWIPE_LEFT2':     { name: 'Swipe Left ×2',    description: 'Move Left (2)',   command: 'left' },
    'SWIPE_RIGHT2':    { name: 'Swipe Right ×2',   description: 'Move Right (2)',  command: 'right' },
    'SWIPE_UP2':       { name: 'Swipe Up ×2',      description: 'Move Up (2)',     command: 'up' },
    'SWIPE_DOWN2':     { name: 'Swipe Down ×2',    description: 'Move Down (2)',   command: 'down' },
    'SWIPE_LEFT3':     { name: 'Swipe Left ×3',    description: 'Move Left (3)',   command: 'left' },
    'SWIPE_RIGHT3':    { name: 'Swipe Right ×3',   description: 'Move Right (3)',  command: 'right' },
    'SWIPE_UP3':       { name: 'Swipe Up ×3',      description: 'Move Up (3)',     command: 'up' },
    'SWIPE_DOWN3':     { name: 'Swipe Down ×3',    description: 'Move Down (3)',   command: 'down' },
    'FAST_SWIPE_UP':   { name: 'Fast Swipe Up',    description: 'Fast Up',         command: 'fast_up' },
    'FAST_SWIPE_DOWN': { name: 'Fast Swipe Down',  description: 'Fast Down',       command: 'fast_down' },
    'ZOOM_IN':         { name: 'Zoom In',           description: 'Zoom In',         command: 'zoom_in' },
    'ZOOM_OUT':        { name: 'Zoom Out',          description: 'Zoom Out',        command: 'zoom_out' },
    'DRAG':            { name: 'Drag',              description: 'Drag Object',     command: 'drag' },
    'DROP':            { name: 'Drop',              description: 'Drop Object',     command: 'drop' },
    'DRAG2':           { name: 'Drag (grip)',        description: 'Drag (grip)',     command: 'drag' },
    'DROP2':           { name: 'Drop (grip)',        description: 'Drop (grip)',     command: 'drop' },
    'DRAG3':           { name: 'Drag (ok)',          description: 'Drag (ok)',       command: 'drag' },
    'DROP3':           { name: 'Drop (ok)',          description: 'Drop (ok)',       command: 'drop' },
    'TAP':             { name: 'Tap',               description: 'Tap',             command: 'tap' },
    'DOUBLE_TAP':      { name: 'Double Tap',        description: 'Double Tap',      command: 'double_tap' },
};

// ===== Valid Gesture Names =====
const VALID_GESTURE_NAMES = Object.keys(GESTURE_GUIDE);

// ===== Safe Gesture Name Regex =====
// Allows lowercase static names (e.g. open_palm) and uppercase dynamic events (e.g. SWIPE_LEFT)
const SAFE_GESTURE_RE = /^[a-zA-Z0-9_-]{1,32}$/;

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
