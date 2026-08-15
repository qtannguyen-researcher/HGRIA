/**
 * HGRIA Main Bootstrap
 * Wires all modules together and starts the application
 */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', () => {
    // Create modules
    const gameState = new GameState();
    const renderer = new Renderer('game-canvas');
    const audioManager = new AudioManager();
    const socketClient = new SocketClient(CONFIG.SERVER_URL, gameState);
    const hudManager = new HUDManager();
    const gameEngine = new GameEngine(gameState, renderer, audioManager);
    const webcamBridge = new WebcamBridge();
    
    // Resume audio on first user interaction
    document.addEventListener('click', () => {
        audioManager.resume();
    }, { once: true });
    
    document.addEventListener('keydown', () => {
        audioManager.resume();
    }, { once: true });
    
    // Keyboard fallback - inject commands into game state
    document.addEventListener('keydown', (e) => {
        const gesture = KEYBOARD_MAP[e.code];
        if (!gesture) return;
        
        e.preventDefault();
        
        // Inject as if it were a WebSocket command
        gameState.enqueueCommand({
            command_id: crypto.randomUUID(),
            gesture_name: gesture,
            command_type: 'KEYBOARD',
            command_value: {},
            confidence: 1.0,
            timestamp: new Date().toISOString(),
        });
    });
    
    // Backend URL setup
    const overlay = document.getElementById('backend-setup-overlay');
    const input = document.getElementById('backend-url-input');
    const button = document.getElementById('backend-url-confirm');
    
    /**
     * Validate URL and save backend URL, then connect
     * @param {string} url - Backend URL
     */
    function saveAndConnect(url) {
        if (!url.startsWith('https://')) {
            hudManager.showError('URL phải bắt đầu bằng https://');
            return;
        }
        localStorage.setItem('hgria_backend_url', url);
        window.HGRIA_BACKEND_URL = url;
        overlay.style.display = 'none';
        socketClient.reconnect(url);
        webcamBridge.start(url);
    }
    
    // Connect button handler
    button.addEventListener('click', () => {
        saveAndConnect(input.value.trim());
    });
    
    // Enter key to submit
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            saveAndConnect(input.value.trim());
        }
    });
    
    // Webcam denied handler
    window.addEventListener('webcam_denied', (e) => {
        hudManager.showError('Webcam bị từ chối. Dùng bàn phím để điều khiển.');
    });
    
    // Show overlay if no server URL configured
    if (!CONFIG.SERVER_URL || CONFIG.SERVER_URL === 'http://localhost:5000') {
        overlay.style.display = 'flex';
    } else {
        socketClient.connect();
        webcamBridge.start(CONFIG.SERVER_URL);
    }
    
    // Start game engine
    gameEngine.start();
    
    // HUD update loop
    let lastFrameTime = performance.now();
    function updateHUD() {
        const now = performance.now();
        const frameDelta = now - lastFrameTime;
        lastFrameTime = now;
        
        hudManager.update(gameState, frameDelta);
        requestAnimationFrame(updateHUD);
    }
    updateHUD();
    
    // Log startup
    console.log('HGRIA initialized');
    console.log('Server URL:', CONFIG.SERVER_URL);
    console.log('Keyboard fallback enabled');
});

// Export for debugging
if (typeof window !== 'undefined') {
    window.HGRIA = {
        version: '1.0.0',
    };
}
