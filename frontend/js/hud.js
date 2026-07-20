/**
 * HGRIA HUD Manager
 * Updates HUD DOM elements based on game state
 */
class HUDManager {
    #elements = {};
    #fpsBuffer = new Array(30).fill(16.7);
    #fpsPtr = 0;
    
    constructor() {
        this.#cacheElements();
    }
    
    /**
     * Cache DOM element references
     */
    #cacheElements() {
        this.#elements = {
            gestureName: document.getElementById('hud-gesture-name'),
            confidenceBar: document.getElementById('hud-confidence-fill'),
            confidencePct: document.getElementById('hud-confidence-pct'),
            systemState: document.getElementById('hud-state'),
            fps: document.getElementById('hud-fps'),
            latency: document.getElementById('hud-latency'),
            connDot: document.getElementById('hud-conn-dot'),
            score: document.getElementById('hud-score'),
            lives: document.getElementById('hud-lives'),
        };
    }
    
    /**
     * Update all HUD elements
     * @param {GameState} state - Current game state
     * @param {number} frameDeltaMs - Frame delta time in ms
     */
    update(state, frameDeltaMs) {
        // Rolling FPS average
        this.#fpsBuffer[this.#fpsPtr++ % 30] = frameDeltaMs;
        const avgDelta = this.#fpsBuffer.reduce((a, b) => a + b, 0) / 30;
        const fps = Math.round(1000 / avgDelta);
        
        // Gesture name
        if (this.#elements.gestureName) {
            this.#elements.gestureName.textContent = safeGestureName(state.currentGesture) || '—';
        }
        
        // Confidence bar and percentage
        const pct = Math.round((state.currentConfidence || 0) * 100);
        const confColour = pct >= 75 ? '#27ae60' : pct >= 50 ? '#f39c12' : '#e74c3c';
        
        if (this.#elements.confidenceBar) {
            this.#elements.confidenceBar.style.width = `${pct}%`;
            this.#elements.confidenceBar.style.backgroundColor = confColour;
        }
        if (this.#elements.confidencePct) {
            this.#elements.confidencePct.textContent = `${pct}%`;
        }
        
        // System state
        if (this.#elements.systemState) {
            this.#elements.systemState.textContent = (state.systemState || 'idle').toUpperCase();
        }
        
        // FPS with colour coding
        if (this.#elements.fps) {
            this.#elements.fps.textContent = `${fps} FPS`;
            if (fps >= 28) {
                this.#elements.fps.style.color = '#27ae60';
            } else if (fps >= 20) {
                this.#elements.fps.style.color = '#f39c12';
            } else {
                this.#elements.fps.style.color = '#e74c3c';
            }
        }
        
        // Latency with colour coding
        const latencyMs = state.latencyMs || 0;
        if (this.#elements.latency) {
            this.#elements.latency.textContent = `${latencyMs} ms`;
            if (latencyMs <= 50) {
                this.#elements.latency.style.color = '#27ae60';
            } else if (latencyMs <= 100) {
                this.#elements.latency.style.color = '#f39c12';
            } else {
                this.#elements.latency.style.color = '#e74c3c';
            }
        }
        
        // Connection dot
        if (this.#elements.connDot) {
            const status = state.connectionStatus || 'disconnected';
            this.#elements.connDot.className = `conn-dot conn-dot--${status}`;
        }
        
        // Score
        if (this.#elements.score) {
            this.#elements.score.textContent = `Score: ${state.score || 0}`;
        }
        
        // Lives (hearts)
        if (this.#elements.lives) {
            const lives = state.lives || 0;
            this.#elements.lives.textContent = '\u2764'.repeat(Math.max(0, lives));
        }
    }
    
    /**
     * Show an error message
     * @param {string} message
     */
    showError(message) {
        // Could add error element here
        console.error('HUD Error:', message);
    }
    
    /**
     * Clear any error display
     */
    clearError() {
        // Clear error element
    }
}
