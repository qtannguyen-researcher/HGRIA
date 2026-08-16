/**
 * HGRIA Renderer
 * Canvas 2D renderer — draws the obstacle runner game.
 * Receives player position and obstacles from the GameEngine reference
 * passed into render().
 */
class Renderer {
    #canvas;
    #ctx;
    #dpr;
    #width  = 0;
    #height = 0;

    /** @param {string} canvasId */
    constructor(canvasId) {
        this.#canvas = document.getElementById(canvasId);
        if (!this.#canvas) throw new Error(`Canvas '${canvasId}' not found`);

        this.#ctx = this.#canvas.getContext('2d');
        this.#dpr = window.devicePixelRatio || 1;

        this.#scaleForDPR();
        window.addEventListener('resize', () => this.#scaleForDPR());
    }

    // ── DPR scaling ───────────────────────────────────────────────────────
    #scaleForDPR() {
        const rect = this.#canvas.getBoundingClientRect();
        this.#width  = rect.width;
        this.#height = rect.height;

        this.#canvas.width  = this.#width  * this.#dpr;
        this.#canvas.height = this.#height * this.#dpr;

        this.#ctx.scale(this.#dpr, this.#dpr);
    }

    clear() {
        this.#ctx.clearRect(0, 0, this.#width, this.#height);
    }

    /**
     * @param {GameState}  state
     * @param {GameEngine} engine  — provides getPlayerPosition() and getObstacles()
     */
    render(state, engine) {
        this.clear();
        this.#drawBackground();
        this.#drawGround();

        const { x: px, y: py } = engine.getPlayerPosition();
        const obstacles = engine.getObstacles();

        this.#drawObstacles(obstacles);
        this.#drawPlayer(px, py, state);

        if (state.paused && !state.gameOver) {
            this.#drawPauseOverlay();
        }

        if (state.gameOver) {
            this.#drawGameOverOverlay(state);
        }

        if (state.errorMessage) {
            this.#drawErrorBanner(state.errorMessage);
        }
    }

    // ── Layers ─────────────────────────────────────────────────────────────

    #drawBackground() {
        const ctx = this.#ctx;
        const w = this.#width;
        const h = this.#height;

        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, '#1a1a2e');
        grad.addColorStop(1, '#16213e');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);

        // Subtle grid
        ctx.strokeStyle = 'rgba(255,255,255,0.04)';
        ctx.lineWidth = 1;
        const grid = 50;
        for (let x = 0; x < w; x += grid) {
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
        }
        for (let y = 0; y < h; y += grid) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
        }
    }

    #drawGround() {
        const ctx = this.#ctx;
        const w = this.#width;
        const groundY = this.#height * 0.85;

        // Ground fill
        ctx.fillStyle = '#0f3460';
        ctx.fillRect(0, groundY, w, this.#height - groundY);

        // Ground line
        ctx.strokeStyle = '#27ae60';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(0, groundY);
        ctx.lineTo(w, groundY);
        ctx.stroke();
    }

    /**
     * Draw the player circle with a simple "running" bob and boost glow.
     * @param {number} px
     * @param {number} py
     * @param {GameState} state
     */
    #drawPlayer(px, py, state) {
        const ctx = this.#ctx;
        const r   = 22; // PLAYER_RADIUS

        const boosted = state.speedBoostActive;

        // Glow ring when boosted
        if (boosted) {
            ctx.shadowColor = '#f39c12';
            ctx.shadowBlur  = 20;
        }

        // Body
        ctx.fillStyle = '#e94560';
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fill();

        // Eye — always faces right
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(px + r * 0.35, py - r * 0.2, r * 0.22, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#1a1a2e';
        ctx.beginPath();
        ctx.arc(px + r * 0.42, py - r * 0.18, r * 0.1, 0, Math.PI * 2);
        ctx.fill();

        ctx.shadowBlur  = 0;
        ctx.shadowColor = 'transparent';
    }

    /**
     * Draw all obstacles.
     * @param {Array<{x,y,w,h,cleared}>} obstacles
     */
    #drawObstacles(obstacles) {
        const ctx = this.#ctx;

        for (const obs of obstacles) {
            if (obs.cleared) continue;

            // Shadow under obstacle
            ctx.fillStyle = 'rgba(0,0,0,0.3)';
            ctx.fillRect(obs.x + 3, obs.y + obs.h, obs.w - 6, 6);

            // Obstacle body — red-ish brick
            ctx.fillStyle = '#c0392b';
            ctx.fillRect(obs.x, obs.y, obs.w, obs.h);

            // Highlight edge
            ctx.strokeStyle = '#e74c3c';
            ctx.lineWidth = 2;
            ctx.strokeRect(obs.x + 1, obs.y + 1, obs.w - 2, obs.h - 2);

            // Inner cross detail
            ctx.strokeStyle = 'rgba(255,255,255,0.12)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(obs.x, obs.y + obs.h / 2);
            ctx.lineTo(obs.x + obs.w, obs.y + obs.h / 2);
            ctx.moveTo(obs.x + obs.w / 2, obs.y);
            ctx.lineTo(obs.x + obs.w / 2, obs.y + obs.h);
            ctx.stroke();
        }
    }

    #drawPauseOverlay() {
        const ctx = this.#ctx;
        const w = this.#width;
        const h = this.#height;

        ctx.fillStyle = 'rgba(0,0,0,0.65)';
        ctx.fillRect(0, 0, w, h);

        ctx.fillStyle = '#fff';
        ctx.font = 'bold 48px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('PAUSED', w / 2, h / 2);

        ctx.font = '18px sans-serif';
        ctx.fillStyle = '#a0a0a0';
        ctx.fillText('Use "stop" gesture or press P to resume', w / 2, h / 2 + 44);

        ctx.textAlign = 'left';
    }

    #drawGameOverOverlay(state) {
        const ctx = this.#ctx;
        const w = this.#width;
        const h = this.#height;

        ctx.fillStyle = 'rgba(0,0,0,0.82)';
        ctx.fillRect(0, 0, w, h);

        ctx.fillStyle = '#e94560';
        ctx.font = 'bold 56px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('GAME OVER', w / 2, h / 2 - 40);

        ctx.fillStyle = '#27ae60';
        ctx.font = 'bold 32px sans-serif';
        ctx.fillText(`Score: ${state.score}`, w / 2, h / 2 + 20);

        ctx.fillStyle = '#a0a0a0';
        ctx.font = '18px sans-serif';
        ctx.fillText('Use "victory" gesture or press R to restart', w / 2, h / 2 + 68);

        ctx.textAlign = 'left';
    }

    #drawErrorBanner(message) {
        const ctx = this.#ctx;
        const w   = this.#width;

        ctx.fillStyle = 'rgba(192,57,43,0.88)';
        ctx.fillRect(0, 0, w, 36);

        ctx.fillStyle = '#fff';
        ctx.font = '13px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(message, w / 2, 23);
        ctx.textAlign = 'left';
    }

    /** @returns {{ width: number, height: number }} */
    getDimensions() {
        return { width: this.#width, height: this.#height };
    }
}
