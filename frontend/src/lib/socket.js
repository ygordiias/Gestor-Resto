import { io } from 'socket.io-client';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

class SocketService {
  constructor() {
    this.socket = null;
    this.listeners = new Map();
    this.isConnecting = false;
  }

  connect() {
    // Evita múltiplas conexões simultâneas
    if (this.socket?.connected || this.isConnecting) return;
    
    this.isConnecting = true;

    this.socket = io(BACKEND_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
    });

    this.socket.on('connect', () => {
      this.isConnecting = false;
      console.log('Socket connected:', this.socket.id);
    });

    this.socket.on('disconnect', () => {
      console.log('Socket disconnected');
    });

    this.socket.on('connect_error', (error) => {
      this.isConnecting = false;
      console.error('Socket connection error:', error);
    });
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.isConnecting = false;
    }
  }

  joinRoom(room) {
    if (this.socket?.connected) {
      this.socket.emit('join_room', { room });
    }
  }

  leaveRoom(room) {
    if (this.socket?.connected) {
      this.socket.emit('leave_room', { room });
    }
  }

  on(event, callback) {
    if (!this.socket) return;
    
    // Remove listener anterior se existir para evitar duplicatas
    if (this.listeners.has(event)) {
      this.socket.off(event, this.listeners.get(event));
    }
    
    this.socket.on(event, callback);
    this.listeners.set(event, callback);
  }

  off(event) {
    if (!this.socket) return;
    
    if (this.listeners.has(event)) {
      this.socket.off(event, this.listeners.get(event));
      this.listeners.delete(event);
    }
  }

  // Remove todos os listeners de um componente
  offAll(events) {
    events.forEach(event => this.off(event));
  }

  emit(event, data) {
    if (this.socket?.connected) {
      this.socket.emit(event, data);
    }
  }
}

export const socketService = new SocketService();
export default socketService;
