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
            this.#stopPing();
            this.#scheduleReconnect();
        });
        
        socket.on('connect_error', (error) => {
            console.warn('Connection error:', error);
            this.#gameState.connectionStatus = 'disconnected';
            this.#scheduleReconnect();
        });
        
        // Server events
        socket.on('server_info', (data) => {
            this.#gameState.applyServerInfo(data);
        });
        
        socket.on('gesture_command', (data) => {
            this.#gameState.enqueueCommand(data);
        });
        
        socket.on('gesture_update', (data) => {
            this.#gameState.updateGestureDisplay(data);
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
