/**
 * HGRIA Main Bootstrap
 * Wires all modules together and starts the application.
 */

document.addEventListener('DOMContentLoaded', () => {
    window._dbgLog && window._dbgLog('MAIN','#0ff','DOMContentLoaded fired');

    // ── Step 1: GameState ──────────────────────────────────────────────────
    let gameState;
    try {
        gameState = new GameState();
        window._gameState = gameState;
        window._dbgLog && window._dbgLog('MAIN','#0f0','GameState OK');
    } catch(e) {
        window._dbgLog && window._dbgLog('MAIN','#f00','GameState FAILED: ' + e.message);
        console.error('GameState failed:', e);
        return;
    }

    // ── Step 2: Renderer ───────────────────────────────────────────────────
    let renderer;
    try {
        renderer = new Renderer('game-canvas');
        window._dbgLog && window._dbgLog('MAIN','#0f0','Renderer OK dims=' + JSON.stringify(renderer.getDimensions()));
    } catch(e) {
        window._dbgLog && window._dbgLog('MAIN','#f00','Renderer FAILED: ' + e.message);
        console.error('Renderer failed:', e);
        return;
    }

    // ── Step 3: AudioManager ───────────────────────────────────────────────
    let audioManager;
    try {
        audioManager = new AudioManager();
        window._dbgLog && window._dbgLog('MAIN','#0f0','AudioManager OK');
    } catch(e) {
        window._dbgLog && window._dbgLog('MAIN','#f00','AudioManager FAILED: ' + e.message);
        console.error('AudioManager failed:', e);
        return;
    }

    // ── Step 4: SocketClient ───────────────────────────────────────────────
    let socketClient;
    try {
        socketClient = new SocketClient(CONFIG.SERVER_URL, gameState);
        window._dbgLog && window._dbgLog('MAIN','#0f0','SocketClient OK url=' + CONFIG.SERVER_URL);
    } catch(e) {
        window._dbgLog && window._dbgLog('MAIN','#f00','SocketClient FAILED: ' + e.message);
        console.error('SocketClient failed:', e);
        return;
    }

    // ── Step 5: HUDManager ─────────────────────────────────────────────────
    let hudManager;
    try {
        hudManager = new HUDManager();
        window._dbgLog && window._dbgLog('MAIN','#0f0','HUDManager OK');
    } catch(e) {
        window._dbgLog && window._dbgLog('MAIN','#f00','HUDManager FAILED: ' + e.message);
        console.error('HUDManager failed:', e);
        return;
    }

    // ── Step 6: GameEngine ─────────────────────────────────────────────────
    let gameEngine;
    try {
        gameEngine = new GameEngine(gameState, renderer, audioManager);
        window._dbgLog && window._dbgLog('MAIN','#0f0','GameEngine OK');
    } catch(e) {
        window._dbgLog && window._dbgLog('MAIN','#f00','GameEngine FAILED: ' + e.message);
        console.error('GameEngine failed:', e);
        return;
    }

    // ── Step 7: WebcamBridge ───────────────────────────────────────────────
    let webcamBridge;
    try {
        webcamBridge = new WebcamBridge();
        window._dbgLog && window._dbgLog('MAIN','#0f0','WebcamBridge OK');
    } catch(e) {
        window._dbgLog && window._dbgLog('MAIN','#f00','WebcamBridge FAILED: ' + e.message);
        console.error('WebcamBridge failed:', e);
        return;
    }

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

    // ── Webcam denied ─────────────────────────────────────────────────────
    window.addEventListener('webcam_denied', (e) => {
        const err     = (e.detail && e.detail.message) ? e.detail.message : '';
        const errName = (e.detail && e.detail.name)    ? e.detail.name    : '';
        window._dbgLog && window._dbgLog('CAM','#f80','denied: ' + errName + ' — ' + err);

        let msg;
        if (errName === 'NotAllowedError' || err.toLowerCase().includes('permission') || err.toLowerCase().includes('denied')) {
            msg = 'Webcam bị từ chối. Vào Settings > Site permissions > Camera, cho phép rồi tải lại trang.';
        } else if (errName === 'NotReadableError' || err.toLowerCase().includes('in use')) {
            msg = 'Webcam đang bị chiếm bởi app khác. Đóng app đó rồi nhấn Retry.';
        } else if (errName === 'NotFoundError') {
            msg = 'Không tìm thấy webcam.';
        } else if (errName === 'SecurityError' || err.toLowerCase().includes('https')) {
            msg = 'Webcam yêu cầu HTTPS. Dùng ngrok URL bắt đầu bằng https://.';
        } else {
            msg = `Webcam lỗi: ${err || errName || 'unknown'}. Dùng bàn phím để điều khiển.`;
        }
        hudManager.showError(msg);

        const pip = document.getElementById('camera-pip');
        if (pip && !document.getElementById('webcam-retry-btn')) {
            pip.classList.remove('pip-hidden');
            const btn = document.createElement('button');
            btn.id = 'webcam-retry-btn';
            btn.textContent = '🔄 Retry webcam';
            btn.style.cssText = 'position:absolute;bottom:8px;left:50%;transform:translateX(-50%);' +
                'padding:6px 14px;background:#1a73e8;color:#fff;border:none;border-radius:6px;' +
                'cursor:pointer;font-size:13px;z-index:10;';
            btn.addEventListener('click', () => {
                btn.remove();
                webcamBridge.start(window.HGRIA_BACKEND_URL || CONFIG.SERVER_URL);
            });
            pip.appendChild(btn);
        }
    });

    // ── Initial connection ────────────────────────────────────────────────
    const stored = localStorage.getItem('hgria_backend_url');
    if (CONFIG.SERVER_URL && CONFIG.SERVER_URL !== 'http://localhost:5000') {
        window._dbgLog && window._dbgLog('MAIN','#0f0','connecting to CONFIG.SERVER_URL: ' + CONFIG.SERVER_URL);
        socketClient.connect();
        webcamBridge.start(CONFIG.SERVER_URL);
    } else if (stored) {
        window._dbgLog && window._dbgLog('MAIN','#0f0','connecting to stored URL: ' + stored);
        window.HGRIA_BACKEND_URL = stored;
        socketClient.connect();
        webcamBridge.start(stored);
    } else if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        window._dbgLog && window._dbgLog('MAIN','#0f0','connecting to localhost:5000');
        socketClient.connect();
        webcamBridge.start('http://localhost:5000');
    } else {
        window._dbgLog && window._dbgLog('MAIN','#fa0','no server URL — showing overlay');
        if (overlay) overlay.style.display = 'flex';
    }

    // ── Game engine start ─────────────────────────────────────────────────
    gameEngine.start();
    window._dbgLog && window._dbgLog('MAIN','#0f0','game loop started');

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

    window._dbgLog && window._dbgLog('MAIN','#0ff','bootstrap complete');
    console.log('HGRIA initialized | server:', CONFIG.SERVER_URL);
});

if (typeof window !== 'undefined') {
    window.HGRIA = { version: '1.0.0' };
}
