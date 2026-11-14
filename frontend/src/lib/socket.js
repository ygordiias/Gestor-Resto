import { io } from 'socket.io-client';
import api from './api';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const RETRY_MS = 5000;

// O backend novo exige o token no Socket.IO e avisa isso em /api/ping
// (socket_auth: true). O backend antigo não tem esse campo e QUEBRA se
// receber "auth" na conexão, por isso só enviamos o token quando ele avisa.
// Isso permite publicar o frontend antes do backend.
// Resposta positiva fica guardada; negativa ou falha é conferida de novo a
// cada nova tentativa (o backend pode ter sido atualizado nesse meio-tempo).
let socketAuthSupported = false;
const detectSocketAuth = async () => {
  if (socketAuthSupported) return true;
  try {
    const { data } = await api.get('/ping');
    socketAuthSupported = data?.socket_auth === true;
  } catch (e) {
    // Sem resposta: conecta como antes; se o backend novo recusar, a
    // recusa dispara uma nova checagem (handleRefused).
  }
  return socketAuthSupported;
};

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
    this.retryTimer = null;
    this.lastOrderCount = { kitchen: 0, bar: 0 };
  }

  connect() {
    if (this.socket || this.isConnecting) return;
    
    this.isConnecting = true;

    // O socket é criado na hora (para os .on() já poderem ser registrados) e
    // só conecta depois de saber se o backend exige token.
    this.socket = io(BACKEND_URL, {
      autoConnect: false,
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      randomizationFactor: 0.5,
      timeout: 20000,
    });
    const socket = this.socket;

    socket.on('connect', () => {
      this.isConnecting = false;
      console.log('Socket connected:', socket.id);
    });

    socket.on('disconnect', (reason) => {
      console.log('Socket disconnected:', reason);
      // Derrubado pelo servidor (ex.: usuário desativado ou perfil trocado):
      // o socket.io não reconecta sozinho nesse caso.
      if (reason === 'io server disconnect') this.handleRefused(socket);
    });

    socket.io.on('reconnect_attempt', (attempt) => {
      console.log('[socket] reconnect attempt', attempt);
    });

    socket.io.on('reconnect', (attempt) => {
      console.log('[socket] reconnected after', attempt, 'attempts');
    });

    socket.on('connect_error', (error) => {
      this.isConnecting = false;
      console.warn('[socket] connect_error:', error?.message || error);
      // Recusa do servidor (token ausente, vencido ou usuário desativado):
      // o socket.io NÃO tenta de novo sozinho nesse caso.
      if (!socket.active) this.handleRefused(socket);
    });

    this.openWithAuth(socket);
  }

  // Liga (ou não) o envio do token conforme o backend e conecta.
  openWithAuth(socket) {
    detectSocketAuth().then((needsToken) => {
      if (this.socket !== socket || socket.connected) return; // desconectado nesse meio-tempo
      // Função: lê o token atual a cada (re)conexão.
      socket.auth = needsToken
        ? (cb) => cb({ token: localStorage.getItem('token') || '' })
        : {};
      socket.connect();
    });
  }

  // Nunca fica parado sem tempo real: confere a sessão pela API. Se o token
  // não vale mais (vencido, usuário desativado), a API responde 401 e o
  // interceptor leva ao login. Se a sessão vale (ou a rede caiu), tenta
  // conectar de novo em alguns segundos.
  handleRefused(socket) {
    if (this.retryTimer) return;
    this.retryTimer = setTimeout(() => {}, RETRY_MS); // marca "em andamento"
    api.get('/auth/me')
      .catch(() => {})
      .finally(() => {
        clearTimeout(this.retryTimer);
        if (this.socket !== socket) {
          this.retryTimer = null;
          return;
        }
        this.retryTimer = setTimeout(() => {
          this.retryTimer = null;
          if (this.socket === socket && !socket.connected) this.openWithAuth(socket);
        }, RETRY_MS);
      });
  }

  disconnect() {
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
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
