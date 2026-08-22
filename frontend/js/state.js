/**
 * HGRIA Game State
 * Single source of truth for all game state
 */
class GameState {
    constructor() {
        // Connection state
        this.connectionStatus = 'disconnected'; // "connected" | "disconnected" | "reconnecting"
        
        // System state
        this.systemState = 'idle';
        
        // Current gesture info
        this.currentGesture = '—';
        this.currentConfidence = 0.0;
        
        // Session info
        this.sessionId = null;
        
        // Game metrics
        this.score = 0;
        this.lives = 3;
        this.level = 1;
        
        // Performance metrics
        this.fps = 0;
        this.latencyMs = 0;
        
        // Game state
        this.gameRunning = false;
        this.paused = false;
        this.gameOver = false;
        this.speedBoostActive = false;
        
        // Error state
        this.errorMessage = null;

        // Evaluation mode: URL flag at construction; OR-ed with server config
        // when server_info arrives. When true, UI_BYPASS and keyboard injection
        // must not enqueue commands — only the server pipeline may.
        this.evaluationMode = (typeof CONFIG !== 'undefined' && CONFIG.EVALUATION_MODE);
        
        // Command queue (max 10)
        this.#inputQueue = [];
    }
    
    // Private field
    #inputQueue;
    #MAX_QUEUE = 10;
    
    /**
     * Enqueue a command for processing
     * @param {Object} cmd - Command object
     */
    enqueueCommand(cmd) {
        if (this.#inputQueue.length >= this.#MAX_QUEUE) {
            this.#inputQueue.shift(); // Drop oldest
        }
        this.#inputQueue.push(cmd);
    }
    
    /**
     * Dequeue and return the oldest command
     * @returns {Object|null} - The oldest command or null if queue is empty
     */
    dequeueCommand() {
        return this.#inputQueue.shift() ?? null;
    }

    /** Debug helper — returns current queue length */
    _dbgQueueLen() {
        return this.#inputQueue.length;
    }
    
    /**
     * Update the camera preview PiP with a frame received from the backend.
     * Falls back gracefully when the DOM element is absent.
     * @param {string} dataUrl - data:image/jpeg;base64,... string
     */
    updateFramePreview(dataUrl) {
        // Use an <img> inside the PiP so we don't interfere with the live
        // <video> element used by WebcamBridge in Colab mode.
        let img = document.getElementById('camera-preview-img');
        if (!img) {
            img = document.createElement('img');
            img.id = 'camera-preview-img';
            img.className = 'camera-preview';
            img.alt = 'Camera feed';
            const pip = document.getElementById('camera-pip');
            if (!pip) return;
            // Hide the <video> placeholder; show our <img> instead.
            const video = document.getElementById('camera-preview');
            if (video) video.style.display = 'none';
            pip.insertBefore(img, pip.firstChild);
            pip.classList.remove('pip-hidden');
        }
        img.src = dataUrl;
    }

    /**
     * Update gesture display from server
     * @param {Object} data - { gesture_name, confidence }
     */
    updateGestureDisplay({ gesture_name, confidence }) {
        this.currentGesture = safeGestureName(gesture_name);
        this.currentConfidence = typeof confidence === 'number' ? confidence : 0.0;
    }
    
    /**
     * Update latency from pong response
     * @param {number} sentTimestamp - Original timestamp from ping
     */
    updateLatency(sentTimestamp) {
        if (typeof sentTimestamp === 'number') {
            this.latencyMs = Math.round(performance.now() - sentTimestamp);
        }
    }
    
    /**
     * Apply server info on connect
     * @param {Object} data - { session_id, config }
     */
    applyServerInfo({ session_id, config }) {
        this.sessionId = session_id;
        this.gameRunning = true;
        this.errorMessage = null;
        const serverEval = !!(config && config.evaluation && config.evaluation.mode);
        this.evaluationMode = this.evaluationMode || serverEval ||
            (typeof CONFIG !== 'undefined' && CONFIG.EVALUATION_MODE);
    }
    
    /**
     * Set an error message
     * @param {Object} data - { message }
     */
    setError({ message }) {
        this.errorMessage = typeof message === 'string' ? message : 'Unknown error';
    }
    
    /**
     * Clear the error message
     */
    clearError() {
        this.errorMessage = null;
    }
    
    /**
     * Update system state from server
     * @param {Object} data - { old_state, new_state }
     */
    updateSystemState({ new_state }) {
        this.systemState = typeof new_state === 'string' ? new_state.toLowerCase() : 'idle';
    }
    
    /**
     * Get a snapshot of key state for rendering
     * @returns {Object} - State snapshot
     */
    getSnapshot() {
        return {
            connectionStatus: this.connectionStatus,
            systemState: this.systemState,
            currentGesture: this.currentGesture,
            currentConfidence: this.currentConfidence,
            score: this.score,
            lives: this.lives,
            level: this.level,
            fps: this.fps,
            latencyMs: this.latencyMs,
            gameRunning: this.gameRunning,
            paused: this.paused,
            gameOver: this.gameOver,
            errorMessage: this.errorMessage,
        };
    }
    
    /**
     * Reset game state for new game
     */
    reset() {
        this.score = 0;
        this.lives = 3;
        this.level = 1;
        this.paused = false;
        this.gameOver = false;
        this.speedBoostActive = false;
        this.errorMessage = null;
        this.#inputQueue = [];
    }
}
