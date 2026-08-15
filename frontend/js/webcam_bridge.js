/**
 * HGRIA Webcam Bridge
 * Captures webcam frames and sends them to the backend server
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
        
        this.#backendUrl = backendUrl;
        
        // Create hidden video and canvas elements
        this.#videoEl = document.createElement('video');
        this.#videoEl.style.display = 'none';
        this.#videoEl.width = 640;
        this.#videoEl.height = 480;
        document.body.appendChild(this.#videoEl);
        
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
            
            this.#running = true;
            
            // Start sending frames at 30 FPS
            this.#intervalId = setInterval(
                this.#sendFrame.bind(this),
                Math.floor(1000 / 30)
            );
        } catch (error) {
            this.#running = false;
            window.dispatchEvent(new CustomEvent('webcam_denied', {
                detail: { message: error.message }
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
            this.#videoEl.remove();
            this.#videoEl = null;
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
                        headers: { 'Content-Type': 'application/json' },
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
