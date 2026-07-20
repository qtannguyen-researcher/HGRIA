/**
 * HGRIA Audio Manager
 * Web Audio API based sound effects
 */
class AudioManager {
    constructor() {
        this.#init();
    }
    
    #audioContext = null;
    #initialized = false;
    
    /**
     * Initialize Web Audio API context
     */
    #init() {
        try {
            this.#audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.#initialized = true;
        } catch (e) {
            console.warn('Web Audio API not supported:', e);
            this.#initialized = false;
        }
    }
    
    /**
     * Resume audio context (required after user interaction)
     */
    async resume() {
        if (this.#audioContext && this.#audioContext.state === 'suspended') {
            try {
                await this.#audioContext.resume();
            } catch (e) {
                console.warn('Failed to resume audio context:', e);
            }
        }
    }
    
    /**
     * Play a sound for a gesture
     * @param {string} gestureName - Name of the gesture
     */
    play(gestureName) {
        if (!this.#initialized || !this.#audioContext) {
            return;
        }
        
        // Resume context if suspended (browser autoplay policy)
        if (this.#audioContext.state === 'suspended') {
            this.resume();
        }
        
        // Create a short tone based on gesture
        const frequencies = {
            'open_palm': 440,
            'closed_fist': 330,
            'point_left': 392,
            'point_right': 440,
            'thumb_up': 523,
            'victory': 659,
            'stop': 220,
            'pinch': 587,
            'ok': 784,
        };
        
        const freq = frequencies[gestureName] || 440;
        this.#playTone(freq, 0.1);
    }
    
    /**
     * Play a confirmation sound
     */
    playConfirm() {
        this.#playTone(880, 0.15);
        setTimeout(() => this.#playTone(1100, 0.1), 100);
    }
    
    /**
     * Play an error sound
     */
    playError() {
        this.#playTone(220, 0.2);
    }
    
    /**
     * Play a game over sound
     */
    playGameOver() {
        this.#playTone(440, 0.3);
        setTimeout(() => this.#playTone(330, 0.3), 200);
        setTimeout(() => this.#playTone(220, 0.5), 400);
    }
    
    /**
     * Play a jump sound
     */
    playJump() {
        this.#playTone(600, 0.08);
        setTimeout(() => this.#playTone(800, 0.08), 50);
    }
    
    /**
     * Play a short tone
     * @param {number} frequency - Frequency in Hz
     * @param {number} duration - Duration in seconds
     * @param {number} volume - Volume 0-1
     */
    #playTone(frequency, duration = 0.1, volume = 0.3) {
        if (!this.#initialized) return;
        
        try {
            const ctx = this.#audioContext;
            const oscillator = ctx.createOscillator();
            const gainNode = ctx.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(ctx.destination);
            
            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(frequency, ctx.currentTime);
            
            // Envelope
            gainNode.gain.setValueAtTime(0, ctx.currentTime);
            gainNode.gain.linearRampToValueAtTime(volume, ctx.currentTime + 0.01);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration);
            
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + duration);
        } catch (e) {
            console.warn('Audio playback failed:', e);
        }
    }
    
    /**
     * Check if audio is available
     * @returns {boolean}
     */
    isAvailable() {
        return this.#initialized;
    }
}
