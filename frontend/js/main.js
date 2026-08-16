/**
 * HGRIA Main Bootstrap
 * Wires all modules together and starts the application.
 */

document.addEventListener('DOMContentLoaded', () => {
    // ── Instantiate modules ──────────────────────────────────────────────
    const gameState    = new GameState();
    const renderer     = new Renderer('game-canvas');
    const audioManager = new AudioManager();
    const socketClient = new SocketClient(CONFIG.SERVER_URL, gameState);
    const hudManager   = new HUDManager();
    const gameEngine   = new GameEngine(gameState, renderer, audioManager);
    const webcamBridge = new WebcamBridge();

    // ── Audio resume on first interaction ────────────────────────────────
    const resumeAudio = () => audioManager.resume();
    document.addEventListener('click',   resumeAudio, { once: true });
    document.addEventListener('keydown', resumeAudio, { once: true });

    // ── Keyboard fallback ────────────────────────────────────────────────
    document.addEventListener('keydown', (e) => {
        const gesture = KEYBOARD_MAP[e.code];
        if (!gesture) return;
        e.preventDefault();

        gameState.enqueueCommand({
            command_id:   crypto.randomUUID(),
            gesture_name: gesture,
            command_type: 'KEYBOARD',
            command_value: {},
            confidence:   1.0,
            timestamp:    new Date().toISOString(),
        });
    });

    // ── Backend URL overlay ───────────────────────────────────────────────
    const overlay = document.getElementById('backend-setup-overlay');
    const input   = document.getElementById('backend-url-input');
    const button  = document.getElementById('backend-url-confirm');

    /**
     * Validate, persist, and connect to the given backend URL.
     * @param {string} url
     */
    function saveAndConnect(url) {
        if (!url.startsWith('https://') && !url.startsWith('http://')) {
            hudManager.showError('URL phải bắt đầu bằng https://');
            return;
        }
        localStorage.setItem('hgria_backend_url', url);
        window.HGRIA_BACKEND_URL = url;
        overlay.style.display = 'none';
        socketClient.reconnect(url);
        webcamBridge.start(url);
    }

    button.addEventListener('click', () => saveAndConnect(input.value.trim()));
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') saveAndConnect(input.value.trim());
    });

    // ── Webcam denied → inform user ───────────────────────────────────────
    window.addEventListener('webcam_denied', () => {
        hudManager.showError('Webcam bị từ chối — dùng bàn phím để điều khiển');
    });

    // ── Initial connection ────────────────────────────────────────────────
    if (!CONFIG.SERVER_URL || CONFIG.SERVER_URL === 'http://localhost:5000') {
        // Try localhost silently; overlay only shows on non-localhost deployments
        // that have no stored URL. For localhost, just attempt to connect.
        const stored = localStorage.getItem('hgria_backend_url');
        if (stored) {
            window.HGRIA_BACKEND_URL = stored;
            socketClient.connect();
            webcamBridge.start(stored);
        } else if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            socketClient.connect();
            webcamBridge.start('http://localhost:5000');
        } else {
            overlay.style.display = 'flex';
        }
    } else {
        socketClient.connect();
        webcamBridge.start(CONFIG.SERVER_URL);
    }

    // ── Game engine start ─────────────────────────────────────────────────
    gameEngine.start();

    // ── HUD update loop ───────────────────────────────────────────────────
    let lastFrameTime = performance.now();
    function updateHUD() {
        const now   = performance.now();
        const delta = now - lastFrameTime;
        lastFrameTime = now;

        hudManager.update(gameState, delta);
        requestAnimationFrame(updateHUD);
    }
    updateHUD();

    // ── Debug ─────────────────────────────────────────────────────────────
    console.log('HGRIA initialized | server:', CONFIG.SERVER_URL);
});

if (typeof window !== 'undefined') {
    window.HGRIA = { version: '1.0.0' };
}
