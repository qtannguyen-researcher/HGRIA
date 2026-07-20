/**
 * HGRIA Renderer
 * Canvas 2D rendering with DPR scaling
 */
class Renderer {
    #canvas;
    #ctx;
    #dpr;
    #width = 0;
    #height = 0;
    
    /**
     * @param {string} canvasId - Canvas element ID
     */
    constructor(canvasId) {
        this.#canvas = document.getElementById(canvasId);
        if (!this.#canvas) {
            throw new Error(`Canvas element '${canvasId}' not found`);
        }
        
        this.#ctx = this.#canvas.getContext('2d');
        this.#dpr = window.devicePixelRatio || 1;
        
        this.#scaleForDPR();
        window.addEventListener('resize', () => this.#scaleForDPR());
    }
    
    /**
     * Scale canvas for device pixel ratio
     */
    #scaleForDPR() {
        const rect = this.#canvas.getBoundingClientRect();
        this.#width = rect.width;
        this.#height = rect.height;
        
        this.#canvas.width = this.#width * this.#dpr;
        this.#canvas.height = this.#height * this.#dpr;
        
        this.#ctx.scale(this.#dpr, this.#dpr);
    }
    
    /**
     * Clear the canvas
     */
    clear() {
        this.#ctx.clearRect(0, 0, this.#width, this.#height);
    }
    
    /**
     * Main render function
     * @param {GameState} state - Current game state
     */
    render(state) {
        this.clear();
        this.#drawBackground(state);
        this.#drawEntities(state);
        this.#drawUI(state);
        
        if (state.paused && !state.gameOver) {
            this.#drawPauseOverlay();
        }
        
        if (state.gameOver) {
            this.#drawGameOverOverlay(state);
        }
        
        if (state.errorMessage) {
            this.#drawErrorOverlay(state.errorMessage);
        }
    }
    
    /**
     * Draw background
     * @param {GameState} state
     */
    #drawBackground(state) {
        const ctx = this.#ctx;
        const w = this.#width;
        const h = this.#height;
        
        // Gradient background
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, '#1a1a2e');
        gradient.addColorStop(1, '#16213e');
        
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, w, h);
        
        // Grid pattern
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.lineWidth = 1;
        const gridSize = 40;
        
        for (let x = 0; x < w; x += gridSize) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, h);
            ctx.stroke();
        }
        
        for (let y = 0; y < h; y += gridSize) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(w, y);
            ctx.stroke();
        }
    }
    
    /**
     * Draw game entities (player, obstacles, etc.)
     * @param {GameState} state
     */
    #drawEntities(state) {
        // Placeholder - game logic would go here
        const ctx = this.#ctx;
        const w = this.#width;
        const h = this.#height;
        
        // Draw player placeholder
        const playerX = w / 2;
        const playerY = h * 0.7;
        const playerSize = 50;
        
        ctx.fillStyle = '#e94560';
        ctx.beginPath();
        ctx.arc(playerX, playerY, playerSize / 2, 0, Math.PI * 2);
        ctx.fill();
        
        // Draw ground line
        ctx.strokeStyle = '#27ae60';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(0, h * 0.85);
        ctx.lineTo(w, h * 0.85);
        ctx.stroke();
    }
    
    /**
     * Draw UI elements
     * @param {GameState} state
     */
    #drawUI(state) {
        const ctx = this.#ctx;
        const w = this.#width;
        
        // Current gesture indicator
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(10, 10, 200, 80);
        
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 16px sans-serif';
        ctx.fillText('Gesture:', 20, 35);
        
        ctx.fillStyle = '#e94560';
        ctx.font = 'bold 24px sans-serif';
        ctx.fillText(state.currentGesture || '—', 20, 65);
        
        // Score
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(w - 160, 10, 150, 40);
        
        ctx.fillStyle = '#27ae60';
        ctx.font = 'bold 20px sans-serif';
        ctx.fillText(`Score: ${state.score}`, w - 150, 38);
    }
    
    /**
     * Draw pause overlay
     */
    #drawPauseOverlay() {
        const ctx = this.#ctx;
        const w = this.#width;
        const h = this.#height;
        
        // Semi-transparent overlay
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(0, 0, w, h);
        
        // Pause text
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 48px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('PAUSED', w / 2, h / 2);
        
        ctx.font = '18px sans-serif';
        ctx.fillStyle = '#a0a0a0';
        ctx.fillText('Use "stop" gesture or press P to resume', w / 2, h / 2 + 40);
        
        ctx.textAlign = 'left';
    }
    
    /**
     * Draw game over overlay
     * @param {GameState} state
     */
    #drawGameOverOverlay(state) {
        const ctx = this.#ctx;
        const w = this.#width;
        const h = this.#height;
        
        // Overlay
        ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
        ctx.fillRect(0, 0, w, h);
        
        // Game Over text
        ctx.fillStyle = '#e94560';
        ctx.font = 'bold 56px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('GAME OVER', w / 2, h / 2 - 40);
        
        // Final score
        ctx.fillStyle = '#27ae60';
        ctx.font = 'bold 32px sans-serif';
        ctx.fillText(`Final Score: ${state.score}`, w / 2, h / 2 + 20);
        
        // Restart prompt
        ctx.fillStyle = '#a0a0a0';
        ctx.font = '18px sans-serif';
        ctx.fillText('Press R or use "victory" gesture to restart', w / 2, h / 2 + 70);
        
        ctx.textAlign = 'left';
    }
    
    /**
     * Draw error overlay
     * @param {string} message
     */
    #drawErrorOverlay(message) {
        const ctx = this.#ctx;
        const w = this.#width;
        
        // Error banner at top
        ctx.fillStyle = 'rgba(231, 76, 60, 0.9)';
        const bannerHeight = 40;
        ctx.fillRect(0, 0, w, bannerHeight);
        
        ctx.fillStyle = '#ffffff';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(message, w / 2, 25);
        
        ctx.textAlign = 'left';
    }
    
    /**
     * Get canvas dimensions
     * @returns {{ width: number, height: number }}
     */
    getDimensions() {
        return { width: this.#width, height: this.#height };
    }
}
