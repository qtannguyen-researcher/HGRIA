/**
 * HGRIA WebSocket Client
 * Socket.IO client with exponential backoff reconnection
 */
class SocketClient {
    #url;
    #socket;
    #gameState;
    #retryCount = 0;
    #maxRetries = CONFIG.MAX_RETRY_COUNT;
    #backoffMs = CONFIG.BACKOFF_MS;
    #pingInterval = null;
    #connected = false;
    
    /**
     * @param {string} serverUrl - Server URL
     * @param {GameState} gameState - GameState instance
     */
    constructor(serverUrl, gameState) {
        this.#url = serverUrl;
        this.#gameState = gameState;
    }
    
    /**
     * Connect to the server
     */
    connect() {
        if (this.#socket) {
            this.#socket.disconnect();
        }
        
        this.#socket = io(this.#url, {
            transports: ['websocket', 'polling'],
            reconnection: false, // We handle reconnection manually
            extraHeaders: {
                'ngrok-skip-browser-warning': '1',
            },
        });
        
        this.#setupEventHandlers();
    }
    
    /**
     * Set up Socket.IO event handlers
     */
    #setupEventHandlers() {
        const socket = this.#socket;
        
        socket.on('connect', () => {
            this.#connected = true;
            this.#retryCount = 0;
            this.#gameState.connectionStatus = 'connected';
            this.#gameState.clearError();
            window._dbgLog && window._dbgLog('WS','#0f0','connected to ' + this.#url);
            
            // Send client_ready
            socket.emit('client_ready', {
                client_id: crypto.randomUUID(),
                user_agent: navigator.userAgent,
            });
            
            this.#startPing();
        });
        
        socket.on('disconnect', () => {
            this.#connected = false;
            this.#gameState.connectionStatus = 'disconnected';
            window._dbgLog && window._dbgLog('WS','#f80','disconnected');
            this.#stopPing();
            this.#scheduleReconnect();
        });
        
        socket.on('connect_error', (error) => {
            console.warn('Connection error:', error);
            window._dbgLog && window._dbgLog('WS','#f00','connect_error: ' + error.message);
            this.#gameState.connectionStatus = 'disconnected';
            this.#scheduleReconnect();
        });
        
        // Server events
        socket.on('server_info', (data) => {
            this.#gameState.applyServerInfo(data);
        });
        
        socket.on('gesture_command', (data) => {
            window._dbgLog && window._dbgLog('CMD','#0ff', `gesture_command: ${data.gesture_name} [${data.command_type}]`);
            console.debug('[gesture_command]', data.gesture_name, data.command_type, data.command_value);
            this.#gameState.enqueueCommand(data);
        });
        
        socket.on('gesture_update', (data) => {
            window._dbgLog && window._dbgLog('UPD','#08f', `gesture_update: ${data.gesture_name} (${Math.round((data.confidence||0)*100)}%)`);
            this.#gameState.updateGestureDisplay(data);

            // Client-side shortcut: inject a synthetic command for UI gestures
            // that need instant response regardless of server-side cooldown.
            // Disabled in evaluation mode so commands originate from the pipeline.
            const UI_BYPASS = new Set(['victory', 'stop', 'ok', 'DOUBLE_TAP']);
            if (!isEvaluationMode(this.#gameState) && UI_BYPASS.has(data.gesture_name)) {
                const now = performance.now();
                const key = `_bypass_${data.gesture_name}`;
                const last = this.#gameState[key] || 0;
                // Client-side bypass cooldown: 800ms — long enough to debounce
                // but short enough to feel responsive.
                if (now - last > 800) {
                    this.#gameState[key] = now;
                    this.#gameState.enqueueCommand({
                        command_id:    crypto.randomUUID(),
                        gesture_name:  data.gesture_name,
                        command_type:  'UI',
                        command_value: {},
                        confidence:    data.confidence || 1.0,
                        timestamp:     new Date().toISOString(),
                        _source:       'client_bypass',
                    });
                }
            }
        });
        
        socket.on('system_state_change', (data) => {
            this.#gameState.updateSystemState(data);
        });
        
        socket.on('system_error', (data) => {
            this.#gameState.setError(data);
        });
        
        socket.on('server_shutdown', () => {
            this.#handleShutdown();
        });
        
        socket.on('pong', (data) => {
            if (data && data.timestamp) {
                this.#gameState.updateLatency(data.timestamp);
            }
        });

        socket.on('frame_preview', (data) => {
            if (data && data.image) {
                this.#gameState.updateFramePreview(data.image);
            }
        });
    }
    
    /**
     * Start ping interval
     */
    #startPing() {
        this.#stopPing();
        this.#pingInterval = setInterval(() => {
            if (this.#connected && this.#socket) {
                this.#socket.emit('ping', { timestamp: performance.now() });
            }
        }, CONFIG.PING_INTERVAL_MS);
    }
    
    /**
     * Stop ping interval
     */
    #stopPing() {
        if (this.#pingInterval) {
            clearInterval(this.#pingInterval);
            this.#pingInterval = null;
        }
    }
    
    /**
     * Schedule reconnection with exponential backoff
     */
    #scheduleReconnect() {
        if (this.#retryCount >= this.#maxRetries) {
            this.#gameState.setError({ 
                message: 'Không thể kết nối. Vui lòng kiểm tra Ngrok URL và làm mới trang.' 
            });
            return;
        }
        
        const delay = this.#backoffMs[Math.min(this.#retryCount, this.#backoffMs.length - 1)];
        this.#retryCount++;
        this.#gameState.connectionStatus = 'reconnecting';
        
        setTimeout(() => {
            if (this.#gameState.connectionStatus === 'reconnecting') {
                this.connect();
            }
        }, delay);
    }
    
    /**
     * Handle server shutdown
     */
    #handleShutdown() {
        this.#gameState.connectionStatus = 'disconnected';
        this.#gameState.setError({ message: 'Server disconnected — session ended' });
        this.#stopPing();
        
        if (this.#socket) {
            this.#socket.disconnect();
        }
    }
    
    /**
     * Emit an event to the server
     * @param {string} event - Event name
     * @param {*} data - Event data
     */
    emit(event, data) {
        if (this.#socket && this.#connected) {
            this.#socket.emit(event, data);
        }
    }
    
    /**
     * Disconnect from the server
     */
    disconnect() {
        this.#stopPing();
        if (this.#socket) {
            this.#socket.disconnect();
        }
        this.#connected = false;
    }
    
    /**
     * Check if connected
     * @returns {boolean}
     */
    isConnected() {
        return this.#connected;
    }
    
    /**
     * Reconnect with a new URL
     * @param {string} newUrl - New server URL
     */
    reconnect(newUrl) {
        this.disconnect();
        this.#url = newUrl;
        this.#retryCount = 0;
        this.connect();
    }
}
