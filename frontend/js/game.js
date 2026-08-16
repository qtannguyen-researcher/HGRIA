/**
 * HGRIA Game Engine — Obstacle Runner
 *
 * Mechanic overview
 * -----------------
 * • Player runs along a horizontal lane.
 * • Obstacles (blocks) spawn from the right and scroll left.
 * • Gesture / keyboard commands:
 *     point_left / SWIPE_LEFT* → move player left
 *     point_right / SWIPE_RIGHT* → move player right
 *     thumb_up / SWIPE_UP* / FAST_SWIPE_UP → jump
 *     open_palm / SWIPE_DOWN* → brake (stop horizontal movement)
 *     closed_fist / FAST_SWIPE_DOWN → speed boost
 *     stop / ok → pause toggle
 *     victory / SELECT → restart after game-over
 * • Score increases 1 pt/s while running; +5 pts per obstacle cleared.
 * • Collision → lose 1 life (brief invincibility window prevents multiple hits).
 * • Level increases every 10 pts, speeding up obstacles.
 */

// ── Constants ────────────────────────────────────────────────────────────────
const PLAYER_RADIUS      = 22;
const PLAYER_SPEED       = 220;       // px/s horizontal
const JUMP_FORCE         = 520;       // initial upward velocity px/s
const GRAVITY            = 900;       // px/s²
const SPEED_BOOST_MUL    = 1.6;
const SPEED_BOOST_MS     = 2000;
const INVINCIBILITY_MS   = 1200;      // after a hit
const SCORE_RATE         = 1;         // pts per second
const SCORE_OBSTACLE_CLR = 5;        // pts per cleared obstacle
const LEVEL_SCORE_STEP   = 10;       // pts between level-ups
const OBSTACLE_BASE_SPEED = 180;     // px/s at level 1
const OBSTACLE_SPEED_INC  = 30;      // px/s per level
const OBSTACLE_SPAWN_INTERVAL_MS = 1800;
const SPAWN_INTERVAL_MIN_MS      = 700;

// ── Keyboard map ─────────────────────────────────────────────────────────────
const KEYBOARD_MAP = {
    'ArrowLeft':  'point_left',
    'ArrowRight': 'point_right',
    'Space':      'thumb_up',
    'KeyP':       'stop',
    'KeyS':       'closed_fist',
    'Enter':      'ok',
    'Escape':     'victory',
    'KeyR':       'victory',    // restart shortcut
};

// ── Command handlers ─────────────────────────────────────────────────────────
/** Each handler mutates the private physics state object passed in. */
const COMMAND_HANDLERS = {
    // Static gestures
    'point_left':   (s) => { s.vx = -PLAYER_SPEED; },
    'point_right':  (s) => { s.vx =  PLAYER_SPEED; },
    'open_palm':    (s) => { s.vx = 0; },
    'thumb_up':     (s) => { if (!s.jumping) { s.vy = -JUMP_FORCE; s.jumping = true; } },
    'closed_fist':  (s) => { s.boostEnd = performance.now() + SPEED_BOOST_MS; },
    'stop':         (s) => { s.pauseToggle = true; },
    'ok':           (s) => { s.pauseToggle = true; },
    'victory':      (s) => { s.restartRequest = true; },
    'pinch':        (s) => {},   // no-op in this mode

    // Dynamic: swipes
    'SWIPE_LEFT':   (s) => { s.vx = -PLAYER_SPEED; },
    'SWIPE_RIGHT':  (s) => { s.vx =  PLAYER_SPEED; },
    'SWIPE_UP':     (s) => { if (!s.jumping) { s.vy = -JUMP_FORCE;        s.jumping = true; } },
    'SWIPE_DOWN':   (s) => { s.vx = 0; },
    'SWIPE_LEFT2':  (s) => { s.vx = -PLAYER_SPEED * 1.5; },
    'SWIPE_RIGHT2': (s) => { s.vx =  PLAYER_SPEED * 1.5; },
    'SWIPE_UP2':    (s) => { if (!s.jumping) { s.vy = -JUMP_FORCE * 1.3;  s.jumping = true; } },
    'SWIPE_DOWN2':  (s) => { s.vx = 0; },
    'SWIPE_LEFT3':  (s) => { s.vx = -PLAYER_SPEED * 2; },
    'SWIPE_RIGHT3': (s) => { s.vx =  PLAYER_SPEED * 2; },
    'SWIPE_UP3':    (s) => { if (!s.jumping) { s.vy = -JUMP_FORCE * 1.6;  s.jumping = true; } },
    'SWIPE_DOWN3':  (s) => { s.vx = 0; },

    // Dynamic: fast
    'FAST_SWIPE_UP':   (s) => { s.vy = -JUMP_FORCE * 2;  s.jumping = true; },
    'FAST_SWIPE_DOWN': (s) => { s.vx = 0; },

    // Dynamic: zoom — no direct effect in runner, swallow silently
    'ZOOM_IN':  (s) => {},
    'ZOOM_OUT': (s) => {},

    // Dynamic: drag/drop — no-op
    'DRAG': (s) => {}, 'DROP': (s) => {},
    'DRAG2':(s) => {}, 'DROP2':(s) => {},
    'DRAG3':(s) => {}, 'DROP3':(s) => {},

    // Dynamic: tap
    'TAP':        (s) => { s.pauseToggle = true; },
    'DOUBLE_TAP': (s) => { s.restartRequest = true; },
};

// ── Obstacle factory ─────────────────────────────────────────────────────────
/**
 * @param {number} canvasW
 * @param {number} groundY
 * @param {number} level
 * @returns {{ x, y, w, h, speed, cleared }}
 */
function spawnObstacle(canvasW, groundY, level) {
    const speed = OBSTACLE_BASE_SPEED + OBSTACLE_SPEED_INC * (level - 1);
    const h = 28 + Math.random() * 28;      // 28–56 px tall
    const w = 22 + Math.random() * 22;      // 22–44 px wide
    return {
        x: canvasW + w,
        y: groundY - h,
        w,
        h,
        speed,
        cleared: false,
    };
}

// ── GameEngine ────────────────────────────────────────────────────────────────
class GameEngine {
    // External references
    #state;
    #renderer;
    #audio;

    // Loop control
    #running = false;
    #lastTime = 0;
    #accumulator = 0;
    static #FIXED_STEP = 1000 / 60;
    static #MAX_DELTA  = 100;

    // Physics state — plain object, NOT stored in GameState (keeps game logic private)
    #phys = {
        x: 0, y: 0,
        vx: 0, vy: 0,
        jumping: false,
        boostEnd: 0,
        pauseToggle: false,
        restartRequest: false,
    };

    // Obstacles array
    #obstacles = [];
    #nextSpawn  = 0;   // timestamp for next spawn

    // Score accumulator (float) for sub-frame scoring
    #scoreAccum = 0;

    // Invincibility timer
    #invincibleUntil = 0;

    /**
     * @param {GameState} gameState
     * @param {Renderer} renderer
     * @param {AudioManager} audioManager
     */
    constructor(gameState, renderer, audioManager) {
        this.#state    = gameState;
        this.#renderer = renderer;
        this.#audio    = audioManager;
        this.#resetPhys();
    }

    /** Start the game loop */
    start() {
        this.#running = true;
        this.#state.gameRunning = true;
        this.#state.paused = false;
        this.#lastTime = performance.now();
        this.#nextSpawn = performance.now() + OBSTACLE_SPAWN_INTERVAL_MS;
        requestAnimationFrame((t) => this.#loop(t));
    }

    /** Stop the game loop */
    stop() {
        this.#running = false;
        this.#state.gameRunning = false;
    }

    /** Return player position for renderer */
    getPlayerPosition() {
        return { x: this.#phys.x, y: this.#phys.y };
    }

    /** Return obstacle list for renderer */
    getObstacles() {
        return this.#obstacles;
    }

    /** Reset physics state to initial positions */
    #resetPhys() {
        const dims = this.#renderer.getDimensions();
        const groundY = dims.height * 0.85;
        this.#phys = {
            x: dims.width * 0.2,
            y: groundY - PLAYER_RADIUS,
            vx: 0,
            vy: 0,
            jumping: false,
            boostEnd: 0,
            pauseToggle: false,
            restartRequest: false,
        };
        this.#obstacles = [];
        this.#scoreAccum = 0;
        this.#invincibleUntil = 0;
        this.#nextSpawn = performance.now() + OBSTACLE_SPAWN_INTERVAL_MS;
    }

    /** Full game reset */
    #doRestart() {
        this.#resetPhys();
        this.#state.reset();
    }

    // ── Main loop ──────────────────────────────────────────────────────────
    #loop(timestamp) {
        if (!this.#running) return;
        requestAnimationFrame((t) => this.#loop(t));

        const delta = Math.min(timestamp - this.#lastTime, GameEngine.#MAX_DELTA);
        this.#lastTime = timestamp;

        // Measure FPS in GameState for HUD
        this.#state.fps = Math.round(1000 / delta) || 0;

        // Process input queue every frame regardless of pause
        this.#processInput();

        if (!this.#state.paused && !this.#state.gameOver) {
            this.#accumulator += delta;
            while (this.#accumulator >= GameEngine.#FIXED_STEP) {
                this.#update(GameEngine.#FIXED_STEP, timestamp);
                this.#accumulator -= GameEngine.#FIXED_STEP;
            }
        }

        // Render — pass engine ref so renderer can pull player + obstacles
        this.#renderer.render(this.#state, this);
    }

    // ── Input processing ──────────────────────────────────────────────────
    #processInput() {
        let cmd;
        while ((cmd = this.#state.dequeueCommand()) !== null) {
            const handler = COMMAND_HANDLERS[cmd.gesture_name];
            if (handler) {
                handler(this.#phys);
                this.#audio.play(cmd.gesture_name);
            }
        }

        // Consume flags
        if (this.#phys.pauseToggle) {
            this.#phys.pauseToggle = false;
            if (!this.#state.gameOver) {
                this.#state.paused = !this.#state.paused;
            }
        }

        if (this.#phys.restartRequest) {
            this.#phys.restartRequest = false;
            if (this.#state.gameOver) {
                this.#doRestart();
            }
        }
    }

    // ── Fixed-step physics update ─────────────────────────────────────────
    /**
     * @param {number} dt     fixed step in ms
     * @param {number} now    current timestamp (performance.now())
     */
    #update(dt, now) {
        const dtSec  = dt / 1000;
        const dims   = this.#renderer.getDimensions();
        const groundY = dims.height * 0.85;
        const floorY  = groundY - PLAYER_RADIUS;

        // Speed boost
        const boosted = now < this.#phys.boostEnd;
        let vx = this.#phys.vx * (boosted ? SPEED_BOOST_MUL : 1);
        this.#state.speedBoostActive = boosted;

        // Horizontal movement
        this.#phys.x += vx * dtSec;
        this.#phys.x  = Math.max(PLAYER_RADIUS, Math.min(dims.width - PLAYER_RADIUS, this.#phys.x));

        // Vertical movement (gravity)
        this.#phys.vy += GRAVITY * dtSec;
        this.#phys.y  += this.#phys.vy * dtSec;

        // Ground collision
        if (this.#phys.y >= floorY) {
            this.#phys.y      = floorY;
            this.#phys.vy     = 0;
            this.#phys.jumping = false;
        }

        // Scroll obstacles and score
        this.#updateObstacles(dtSec, dims, groundY, now);

        // Score over time
        this.#scoreAccum += SCORE_RATE * dtSec;
        const earnedPts = Math.floor(this.#scoreAccum);
        if (earnedPts > 0) {
            this.#state.score += earnedPts;
            this.#scoreAccum  -= earnedPts;
        }

        // Level-up
        const newLevel = Math.floor(this.#state.score / LEVEL_SCORE_STEP) + 1;
        if (newLevel > this.#state.level) {
            this.#state.level = newLevel;
        }

        // Spawn new obstacles
        if (now >= this.#nextSpawn) {
            this.#obstacles.push(spawnObstacle(dims.width, groundY, this.#state.level));
            const interval = Math.max(
                SPAWN_INTERVAL_MIN_MS,
                OBSTACLE_SPAWN_INTERVAL_MS - (this.#state.level - 1) * 100
            );
            this.#nextSpawn = now + interval;
        }
    }

    /**
     * Move obstacles, detect clears and collisions.
     * @param {number} dtSec
     * @param {{ width, height }} dims
     * @param {number} groundY
     * @param {number} now
     */
    #updateObstacles(dtSec, dims, groundY, now) {
        const invinc = now < this.#invincibleUntil;

        for (const obs of this.#obstacles) {
            obs.x -= obs.speed * dtSec;

            // Clear — player has passed the right edge of the obstacle
            if (!obs.cleared && obs.x + obs.w < this.#phys.x - PLAYER_RADIUS) {
                obs.cleared = true;
                this.#state.score += SCORE_OBSTACLE_CLR;
            }

            // Collision — AABB vs circle approximation
            if (!invinc && !obs.cleared && this.#circleAABB(this.#phys.x, this.#phys.y, PLAYER_RADIUS, obs)) {
                this.#state.lives--;
                this.#invincibleUntil = now + INVINCIBILITY_MS;
                this.#audio.playError();

                if (this.#state.lives <= 0) {
                    this.#state.gameOver = true;
                    this.#audio.playGameOver();
                }
            }
        }

        // Prune off-screen obstacles
        this.#obstacles = this.#obstacles.filter(o => o.x + o.w > -10);
    }

    /**
     * Simple circle vs AABB collision test.
     * @param {number} cx  circle center x
     * @param {number} cy  circle center y
     * @param {number} r   radius
     * @param {{ x, y, w, h }} rect
     * @returns {boolean}
     */
    #circleAABB(cx, cy, r, rect) {
        const nearX = Math.max(rect.x, Math.min(cx, rect.x + rect.w));
        const nearY = Math.max(rect.y, Math.min(cy, rect.y + rect.h));
        const dx = cx - nearX;
        const dy = cy - nearY;
        return dx * dx + dy * dy < r * r;
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { COMMAND_HANDLERS, KEYBOARD_MAP, GameEngine };
}
