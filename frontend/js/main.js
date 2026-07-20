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
    
    // Connect to server
    socketClient.connect();
    
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
