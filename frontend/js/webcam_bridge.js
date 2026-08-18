/**
 * HGRIA Webcam Bridge
 * Captures webcam frames and sends them to the backend server.
 * Reuses the #camera-preview element from the DOM for the PiP display.
 */
class WebcamBridge {
    #videoEl;
    #canvasEl;
    #stream;
    #backendUrl;
    #intervalId;
    #running = false;

    /**
     * Start capturing webcam frames
     * @param {string} backendUrl - Backend server URL
     */
    async start(backendUrl) {
        if (this.#running) {
            return;
        }

        // getUserMedia requires a secure context (https or localhost).
        if (typeof navigator.mediaDevices === 'undefined' || !navigator.mediaDevices.getUserMedia) {
            window.dispatchEvent(new CustomEvent('webcam_denied', {
                detail: {
                    name: 'SecurityError',
                    message: 'getUserMedia not available — page must be served over HTTPS or localhost',
                }
            }));
            return;
        }

        this.#backendUrl = backendUrl;

        // Reuse the visible PiP video element already in the DOM
        this.#videoEl = document.getElementById('camera-preview');
        if (!this.#videoEl) {
            console.warn('WebcamBridge: #camera-preview element not found');
            return;
        }

        this.#canvasEl = document.createElement('canvas');
        this.#canvasEl.width = 640;
        this.#canvasEl.height = 480;

        try {
            // Request webcam access
            this.#stream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480 }
            });

            this.#videoEl.srcObject = this.#stream;
            await this.#videoEl.play();

            // Show the PiP container now that we have a stream
            const pip = document.getElementById('camera-pip');
            if (pip) {
                pip.classList.remove('pip-hidden');
            }

            this.#running = true;

            // Start sending frames at 30 FPS
            this.#intervalId = setInterval(
                this.#sendFrame.bind(this),
                Math.floor(1000 / 30)
            );
        } catch (error) {
            this.#running = false;
            window.dispatchEvent(new CustomEvent('webcam_denied', {
                detail: { message: error.message, name: error.name }
            }));
        }
    }

    /**
     * Stop capturing webcam frames
     */
    stop() {
        if (this.#intervalId) {
            clearInterval(this.#intervalId);
            this.#intervalId = null;
        }

        if (this.#stream) {
            this.#stream.getTracks().forEach(track => track.stop());
            this.#stream = null;
        }

        if (this.#videoEl) {
            this.#videoEl.srcObject = null;
        }

        // Hide PiP
        const pip = document.getElementById('camera-pip');
        if (pip) {
            pip.classList.add('pip-hidden');
        }

        this.#running = false;
    }

    /**
     * Check if webcam bridge is running
     * @returns {boolean}
     */
    isRunning() {
        return this.#running;
    }

    /**
     * Send a single frame to the backend
     * @private
     */
    async #sendFrame() {
        if (!this.#running || !this.#videoEl || !this.#canvasEl) {
            return;
        }

        try {
            const ctx = this.#canvasEl.getContext('2d');
            // Draw frame as-is — PiP preview also shows un-mirrored frame,
            // so what the user sees matches what the backend processes.
            ctx.drawImage(this.#videoEl, 0, 0, 640, 480);

            const blob = await new Promise((resolve, reject) => {
                this.#canvasEl.toBlob(
                    (b) => b ? resolve(b) : reject(new Error('Canvas toBlob failed')),
                    'image/jpeg',
                    0.7
                );
            });

            const reader = new FileReader();
            reader.onload = async () => {
                try {
                    const base64 = reader.result.split(',')[1];
                    await fetch(this.#backendUrl + '/api/frame', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'ngrok-skip-browser-warning': '1',
                        },
                        body: JSON.stringify({ image: base64 })
                    });
                } catch (e) {
                    console.warn('Frame send failed:', e.message);
                }
            };
            reader.onerror = () => {
                console.warn('Frame read failed');
            };
            reader.readAsDataURL(blob);
        } catch (e) {
            console.warn('Frame capture failed:', e.message);
        }
    }
}
