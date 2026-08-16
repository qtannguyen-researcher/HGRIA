/**
 * HGRIA HUD Manager
 * Updates HUD DOM elements based on game state and shows toast notifications.
 */
class HUDManager {
    #elements = {};
    #fpsBuffer = new Array(30).fill(16.7);
    #fpsPtr = 0;
    #lastConnStatus = null;

    // Toast queue so multiple toasts don't stack weirdly
    #toastQueue = [];
    #toastActive = false;

    constructor() {
        this.#cacheElements();
    }

    /** Cache DOM element references */
    #cacheElements() {
        this.#elements = {
            gestureName:    document.getElementById('hud-gesture-name'),
            confidenceBar:  document.getElementById('hud-confidence-fill'),
            confidencePct:  document.getElementById('hud-confidence-pct'),
            systemState:    document.getElementById('hud-state'),
            fps:            document.getElementById('hud-fps'),
            latency:        document.getElementById('hud-latency'),
            connDot:        document.getElementById('hud-conn-dot'),
            connLabel:      document.getElementById('hud-conn-label'),
            score:          document.getElementById('hud-score'),
            lives:          document.getElementById('hud-lives'),
            toastContainer: document.getElementById('toast-container'),
        };
    }

    /**
     * Update all HUD elements from current game state.
     * @param {GameState} state
     * @param {number} frameDeltaMs
     */
    update(state, frameDeltaMs) {
        // Rolling 30-frame FPS average
        this.#fpsBuffer[this.#fpsPtr++ % 30] = frameDeltaMs;
        const avgDelta = this.#fpsBuffer.reduce((a, b) => a + b, 0) / 30;
        const fps = Math.round(1000 / avgDelta);

        // Gesture name
        const el = this.#elements;
        if (el.gestureName) {
            el.gestureName.textContent = safeGestureName(state.currentGesture) || '—';
        }

        // Confidence bar + percentage
        const pct = Math.round((state.currentConfidence || 0) * 100);
        if (el.confidenceBar) {
            el.confidenceBar.style.width = `${pct}%`;
            el.confidenceBar.className = 'hud-confidence-fill ' + (
                pct >= 75 ? 'conf-good' : pct >= 50 ? 'conf-warn' : 'conf-bad'
            );
        }
        if (el.confidencePct) {
            el.confidencePct.textContent = `${pct}%`;
        }

        // System state
        if (el.systemState) {
            el.systemState.textContent = (state.systemState || 'idle').toUpperCase();
        }

        // FPS
        if (el.fps) {
            el.fps.textContent = `${fps} FPS`;
            el.fps.className = 'hud-stat-value ' + (
                fps >= 28 ? 'fps-good' : fps >= 20 ? 'fps-warn' : 'fps-bad'
            );
        }

        // Latency
        const latencyMs = state.latencyMs || 0;
        if (el.latency) {
            el.latency.textContent = `${latencyMs} ms`;
            el.latency.className = 'hud-stat-value ' + (
                latencyMs <= 50 ? 'lat-good' : latencyMs <= 100 ? 'lat-warn' : 'lat-bad'
            );
        }

        // Connection dot + label — fire toast on status change
        const status = state.connectionStatus || 'disconnected';
        if (el.connDot) {
            el.connDot.className = `conn-dot conn-dot--${status}`;
        }
        if (el.connLabel) {
            const labels = {
                connected:    'Connected',
                disconnected: 'Disconnected',
                reconnecting: 'Reconnecting…',
            };
            el.connLabel.textContent = labels[status] || status;
        }

        if (status !== this.#lastConnStatus) {
            this.#onConnectionChange(status, this.#lastConnStatus);
            this.#lastConnStatus = status;
        }

        // Error toast (shown once per new message)
        if (state.errorMessage && state.errorMessage !== this.#lastError) {
            this.showError(state.errorMessage);
            this.#lastError = state.errorMessage;
        } else if (!state.errorMessage) {
            this.#lastError = null;
        }

        // Score
        if (el.score) {
            el.score.textContent = `Score: ${state.score || 0}`;
        }

        // Lives (hearts)
        if (el.lives) {
            const lives = Math.max(0, state.lives || 0);
            el.lives.textContent = '\u2764'.repeat(lives);
        }
    }

    #lastError = null;

    /**
     * React to connection status transitions with appropriate toasts.
     * @param {string} next
     * @param {string|null} prev
     */
    #onConnectionChange(next, prev) {
        if (next === 'connected') {
            this.#enqueueToast('✓ Backend connected', 'success', 2500);
        } else if (next === 'disconnected' && prev === 'connected') {
            this.#enqueueToast('Connection lost', 'error', 3000);
        } else if (next === 'reconnecting') {
            this.#enqueueToast('Reconnecting…', 'warn', 2000);
        } else if (next === 'disconnected' && prev === null) {
            // initial state — no toast needed
        }
    }

    /**
     * Show an error toast.
     * @param {string} message
     */
    showError(message) {
        this.#enqueueToast(message, 'error', 4000);
    }

    /**
     * Show an info toast.
     * @param {string} message
     * @param {number} [duration=2500]
     */
    showInfo(message, duration = 2500) {
        this.#enqueueToast(message, 'info', duration);
    }

    // ── Toast internals ──────────────────────────────────────────────────

    /**
     * @param {string} message
     * @param {'success'|'error'|'warn'|'info'} type
     * @param {number} duration ms
     */
    #enqueueToast(message, type, duration) {
        this.#toastQueue.push({ message, type, duration });
        if (!this.#toastActive) {
            this.#showNextToast();
        }
    }

    #showNextToast() {
        const container = this.#elements.toastContainer;
        if (!container || this.#toastQueue.length === 0) {
            this.#toastActive = false;
            return;
        }

        this.#toastActive = true;
        const { message, type, duration } = this.#toastQueue.shift();

        const toast = document.createElement('div');
        toast.className = `toast toast--${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        // Auto-dismiss
        setTimeout(() => {
            toast.classList.add('toast--out');
            toast.addEventListener('animationend', () => {
                toast.remove();
                this.#showNextToast();
            }, { once: true });
        }, duration);
    }
}
