import { io } from 'socket.io-client';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Beep sound para notificações (simples, sem biblioteca)
const playBeep = () => {
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.value = 800;
    oscillator.type = 'sine';
    gainNode.gain.value = 0.3;
    
    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.2);
  } catch (e) {
    console.log('Audio not supported');
  }
};

class SocketService {
  constructor() {
    this.socket = null;
    this.listeners = new Map();
    this.isConnecting = false;
    this.lastOrderCount = { kitchen: 0, bar: 0 };
  }

  connect() {
    if (this.socket?.connected || this.isConnecting) return;
    
    this.isConnecting = true;

    this.socket = io(BACKEND_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      timeout: 20000,
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
      // Remove todos os listeners antes de desconectar
      this.listeners.forEach((callback, event) => {
        this.socket.off(event, callback);
      });
      this.listeners.clear();
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

  on(event, callback, options = {}) {
    if (!this.socket) {
      this.connect();
    }
    
    // Remove listener anterior para evitar duplicatas
    if (this.listeners.has(event)) {
      this.socket.off(event, this.listeners.get(event));
    }
    
    // Wrapper para adicionar beep em novos pedidos
    const wrappedCallback = (data) => {
      if (options.playSound && event.includes('update')) {
        const newCount = this.countPendingItems(data, options.itemType);
        const oldCount = this.lastOrderCount[options.itemType] || 0;
        
        if (newCount > oldCount) {
          playBeep();
        }
        this.lastOrderCount[options.itemType] = newCount;
      }
      callback(data);
    };
    
    this.socket.on(event, wrappedCallback);
    this.listeners.set(event, wrappedCallback);
  }

  countPendingItems(orders, itemType) {
    if (!Array.isArray(orders)) return 0;
    let count = 0;
    orders.forEach(order => {
      if (order.items) {
        order.items.forEach(item => {
          if (item.type === itemType && item.status === 'pending') {
            count++;
          }
        });
      }
    });
    return count;
  }

  off(event) {
    if (!this.socket) return;
    
    if (this.listeners.has(event)) {
      this.socket.off(event, this.listeners.get(event));
      this.listeners.delete(event);
    }
  }

  offAll(events) {
    events.forEach(event => this.off(event));
  }

  emit(event, data) {
    if (this.socket?.connected) {
      this.socket.emit(event, data);
    }
  }

  // Método para notificar garçom quando pedido estiver pronto
  notifyWaiter(tableNumber, productName) {
    if (this.socket?.connected) {
      this.socket.emit('item_ready', { tableNumber, productName });
    }
  }
}

export const socketService = new SocketService();
export const playNotificationSound = playBeep;
export default socketService;
