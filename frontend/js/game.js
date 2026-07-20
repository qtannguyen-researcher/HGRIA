/**
 * HGRIA Game Engine
 * Game loop with physics and input processing
 */

// ===== Constants =====
const PLAYER_SPEED = 200;
const JUMP_FORCE = 500;
const GRAVITY = 800;
const SPEED_BOOST_MULTIPLIER = 1.5;
const SPEED_BOOST_DURATION_MS = 2000;

/**
 * Gesture → game action dispatch table
 */
const COMMAND_HANDLERS = {
    'point_left': (state) => {
        state.playerVx = -PLAYER_SPEED;
    },
    'point_right': (state) => {
        state.playerVx = PLAYER_SPEED;
    },
    'open_palm': (state) => {
        state.playerVx = 0;
    },
    'thumb_up': (state) => {
        if (!state.isJumping) {
            state.jumpVelocity = JUMP_FORCE;
            state.isJumping = true;
        }
    },
    'closed_fist': (state) => {
        state.speedBoostActive = true;
        state.speedBoostEndTime = performance.now() + SPEED_BOOST_DURATION_MS;
    },
    'stop': (state) => {
        state.paused = !state.paused;
    },
    'ok': (state) => {
        state.confirmPending = true;
    },
    'victory': (state) => {
        state.selectPending = true;
    },
    'pinch': (state) => {
        state.zoomLevel = Math.min(state.zoomLevel * 1.1, 3.0);
    },
};

/**
 * Keyboard → gesture mapping
 */
const KEYBOARD_MAP = {
    'ArrowLeft': 'point_left',
    'ArrowRight': 'point_right',
    'Space': 'thumb_up',
    'KeyP': 'stop',
    'KeyS': 'closed_fist',
    'Enter': 'ok',
    'Escape': 'victory',
    'Equal': 'pinch', // '+' key
    'NumpadAdd': 'pinch',
};

class GameEngine {
    #state;
    #renderer;
    #audio;
    #lastTime = 0;
    #accumulator = 0;
    #running = false;
    
    // Physics state (not in GameState for encapsulation)
    #playerX = 0;
    #playerY = 0;
    #playerVx = 0;
    #jumpVelocity = 0;
    #isJumping = false;
    #speedBoostActive = false;
    #speedBoostEndTime = 0;
    #zoomLevel = 1.0;
    
    static #FIXED_STEP = 1000 / 60; // 16.7 ms
    static #MAX_DELTA = 100; // cap to prevent spiral-of-death
    
    /**
     * @param {GameState} gameState
     * @param {Renderer} renderer
     * @param {AudioManager} audioManager
     */
    constructor(gameState, renderer, audioManager) {
        this.#state = gameState;
        this.#renderer = renderer;
        this.#audio = audioManager;
        
        // Initialize player position
        const dims = renderer.getDimensions();
        this.#playerX = dims.width / 2;
        this.#playerY = dims.height * 0.7;
    }
    
    /**
     * Start the game loop
     */
    start() {
        this.#running = true;
        this.#state.gameRunning = true;
        this.#state.paused = false;
        this.#lastTime = performance.now();
        requestAnimationFrame((t) => this.#loop(t));
    }
    
    /**
     * Stop the game loop
     */
    stop() {
        this.#running = false;
        this.#state.gameRunning = false;
    }
    
    /**
     * Reset game state
     */
    reset() {
        const dims = this.#renderer.getDimensions();
        this.#playerX = dims.width / 2;
        this.#playerY = dims.height * 0.7;
        this.#playerVx = 0;
        this.#jumpVelocity = 0;
        this.#isJumping = false;
        this.#speedBoostActive = false;
        this.#zoomLevel = 1.0;
        this.#state.reset();
    }
    
    /**
     * Main game loop
     * @param {number} timestamp
     */
    #loop(timestamp) {
        if (!this.#running) return;
        
        requestAnimationFrame((t) => this.#loop(t));
        
        const delta = Math.min(timestamp - this.#lastTime, GameEngine.#MAX_DELTA);
        this.#lastTime = timestamp;
        
        // Update FPS measurement
        this.#state.fps = Math.round(1000 / delta) || 0;
        
        // Process input from WebSocket queue
        this.#processInput();
        
        // Update physics if not paused
        if (!this.#state.paused && !this.#state.gameOver) {
            this.#accumulator += delta;
            
            while (this.#accumulator >= GameEngine.#FIXED_STEP) {
                this.#update(GameEngine.#FIXED_STEP);
                this.#accumulator -= GameEngine.#FIXED_STEP;
            }
        }
        
        // Always render
        this.#renderer.render(this.#state);
    }
    
    /**
     * Process input from command queue
     */
    #processInput() {
        let cmd;
        while ((cmd = this.#state.dequeueCommand()) !== null) {
            const handler = COMMAND_HANDLERS[cmd.gesture_name];
            if (handler) {
                handler(this.#state);
                this.#audio.play(cmd.gesture_name);
            }
        }
        
        // Handle pending actions
        if (this.#state.selectPending) {
            this.#state.selectPending = false;
            this.reset();
        }
        
        if (this.#state.confirmPending) {
            this.#state.confirmPending = false;
            // Confirm action
        }
    }
    
    /**
     * Update game physics
     * @param {number} dt - Delta time in ms
     */
    #update(dt) {
        const dtSec = dt / 1000;
        const dims = this.#renderer.getDimensions();
        const groundY = dims.height * 0.85;
        
        // Apply speed boost
        let speed = this.#playerVx;
        if (this.#speedBoostActive) {
            if (performance.now() >= this.#speedBoostEndTime) {
                this.#speedBoostActive = false;
            } else {
                speed *= SPEED_BOOST_MULTIPLIER;
            }
        }
        
        // Update horizontal position
        this.#playerX += speed * dtSec;
        
        // Keep player in bounds
        this.#playerX = Math.max(25, Math.min(dims.width - 25, this.#playerX));
        
        // Apply gravity
        this.#jumpVelocity -= GRAVITY * dtSec;
        this.#playerY -= this.#jumpVelocity * dtSec;
        
        // Ground collision
        if (this.#playerY >= groundY) {
            this.#playerY = groundY;
            this.#jumpVelocity = 0;
            this.#isJumping = false;
        }
        
        // Check collisions with obstacles (placeholder)
        this.#checkCollisions();
        
        // Check win/loss conditions
        this.#checkWinLoss();
    }
    
    /**
     * Check collisions with obstacles
     */
    #checkCollisions() {
        // Placeholder - collision detection logic would go here
    }
    
    /**
     * Check win/loss conditions
     */
    #checkWinLoss() {
        // Lose a life if player falls below screen
        const dims = this.#renderer.getDimensions();
        if (this.#playerY > dims.height + 50) {
            this.#state.lives--;
            if (this.#state.lives <= 0) {
                this.#state.gameOver = true;
                this.#audio.playGameOver();
            } else {
                // Reset player position
                this.#playerX = dims.width / 2;
                this.#playerY = dims.height * 0.7;
                this.#jumpVelocity = 0;
            }
        }
    }
    
    /**
     * Get player position for renderer
     * @returns {{ x: number, y: number }}
     */
    getPlayerPosition() {
        return { x: this.#playerX, y: this.#playerY };
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { COMMAND_HANDLERS, KEYBOARD_MAP, GameEngine };
}
