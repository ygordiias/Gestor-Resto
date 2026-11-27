import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_URL = `${BACKEND_URL}/api`;

// Storage keys for offline data
const STORAGE_KEYS = {
  PENDING_ORDERS: 'pendingOrders',
  CACHED_PRODUCTS: 'cachedProducts',
  CACHED_CATEGORIES: 'cachedCategories',
  CACHED_TABLES: 'cachedTables',
  LAST_SYNC: 'lastSync',
};

// Create axios instance
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle errors and offline fallback
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Rede indisponível / timeout / servidor offline: apenas propaga o erro
    // para o chamador tratar (com fallback local quando aplicável). NÃO faz
    // window.location.href para evitar loops de redirecionamento e telas
    // brancas quando o backend está temporariamente inacessível.
    const isNetworkError =
      !error.response || error.code === 'ECONNABORTED' || error.message === 'Network Error';

    if (isNetworkError) {
      console.warn('[api] network error:', error.message);
      return Promise.reject(error);
    }

    // 401 apenas em rotas autenticadas: limpa sessão e volta ao login.
    // Evita redirecionar durante a própria tela de login (loop).
    if (error.response?.status === 401) {
      const path = window.location.pathname || '';
      const isAuthEndpoint = (error.config?.url || '').includes('/auth/login');
      if (!isAuthEndpoint && path !== '/login') {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Helper: Check if online
const isOnline = () => navigator.onLine;

// Helper: Save to localStorage
const saveToLocal = (key, data) => {
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch (e) {
    console.warn('LocalStorage full, clearing old data');
    localStorage.removeItem(STORAGE_KEYS.CACHED_PRODUCTS);
  }
};

// Helper: Get from localStorage
const getFromLocal = (key) => {
  try {
    const data = localStorage.getItem(key);
    return data ? JSON.parse(data) : null;
  } catch (e) {
    return null;
  }
};

// Helper: Add pending order for sync
const addPendingOrder = (order) => {
  const pending = getFromLocal(STORAGE_KEYS.PENDING_ORDERS) || [];
  pending.push({ ...order, _localId: Date.now(), _pending: true });
  saveToLocal(STORAGE_KEYS.PENDING_ORDERS, pending);
};

// Helper: Remove synced order
const removePendingOrder = (localId) => {
  const pending = getFromLocal(STORAGE_KEYS.PENDING_ORDERS) || [];
  saveToLocal(STORAGE_KEYS.PENDING_ORDERS, pending.filter(o => o._localId !== localId));
};

// Helper: Get pending orders
export const getPendingOrders = () => getFromLocal(STORAGE_KEYS.PENDING_ORDERS) || [];

// Sync pending orders when online
export const syncPendingOrders = async () => {
  if (!isOnline()) return { synced: 0, failed: 0 };
  
  const pending = getPendingOrders();
  let synced = 0;
  let failed = 0;
  
  for (const order of pending) {
    try {
      const { _localId, _pending, ...orderData } = order;
      await api.post('/orders', orderData);
      removePendingOrder(_localId);
      synced++;
    } catch (e) {
      failed++;
    }
  }
  
  return { synced, failed };
};

// Auth
export const authAPI = {
  login: (data) => api.post('/auth/login', data),
  getMe: () => api.get('/auth/me'),
};

// Users
export const usersAPI = {
  getAll: () => api.get('/users'),
  create: (data) => api.post('/users', data),
  update: (id, data) => api.put(`/users/${id}`, data),
  delete: (id) => api.delete(`/users/${id}`),
};

// Categories - with offline cache
export const categoriesAPI = {
  getAll: async () => {
    try {
      const response = await api.get('/categories');
      saveToLocal(STORAGE_KEYS.CACHED_CATEGORIES, response.data);
      return response;
    } catch (e) {
      if (!isOnline()) {
        const cached = getFromLocal(STORAGE_KEYS.CACHED_CATEGORIES);
        if (cached) return { data: cached };
      }
      throw e;
    }
  },
  create: (data) => api.post('/categories', data),
  update: (id, data) => api.put(`/categories/${id}`, data),
  delete: (id) => api.delete(`/categories/${id}`),
};

// Products - with offline cache
export const productsAPI = {
  getAll: async () => {
    try {
      const response = await api.get('/products');
      saveToLocal(STORAGE_KEYS.CACHED_PRODUCTS, response.data);
      return response;
    } catch (e) {
      if (!isOnline()) {
        const cached = getFromLocal(STORAGE_KEYS.CACHED_PRODUCTS);
        if (cached) return { data: cached };
      }
      throw e;
    }
  },
  get: (id) => api.get(`/products/${id}`),
  create: (data) => api.post('/products', data),
  update: (id, data) => api.put(`/products/${id}`, data),
  delete: (id) => api.delete(`/products/${id}`),
};

// Tables - with offline cache
export const tablesAPI = {
  getAll: async () => {
    try {
      const response = await api.get('/tables');
      saveToLocal(STORAGE_KEYS.CACHED_TABLES, response.data);
      return response;
    } catch (e) {
      if (!isOnline()) {
        const cached = getFromLocal(STORAGE_KEYS.CACHED_TABLES);
        if (cached) return { data: cached };
      }
      throw e;
    }
  },
  create: (data) => api.post('/tables', data),
  update: (id, data) => api.put(`/tables/${id}`, data),
  delete: (id) => api.delete(`/tables/${id}`),
};

// Orders - with offline support
export const ordersAPI = {
  getAll: (params) => api.get('/orders', { params }),
  createOnline: (data) => api.post('/orders/online', data),
  getOpen: async () => {
    try {
      const response = await api.get('/orders/open');
      return response;
    } catch (e) {
      // Return pending orders if offline
      if (!isOnline()) {
        const pending = getPendingOrders();
        return { data: pending };
      }
      throw e;
    }
  },
  get: (id) => api.get(`/orders/${id}`),
  // Observação nova para o KDS (qualquer pedido): pedido inteiro ou um item.
  addObservation: (orderId, text, itemId = null) =>
    api.post(`/orders/${orderId}/observacao`, itemId ? { text, item_id: itemId } : { text }),
  ackObservation: (orderId, obsId, station) =>
    api.post(`/orders/${orderId}/observacao/${obsId}/ciente`, { station }),
  getByTable: (tableId) => api.get(`/orders/table/${tableId}`),
  create: async (data) => {
    try {
      const response = await api.post('/orders', data);
      return response;
    } catch (e) {
      // Save offline if network error
      if (!isOnline() || e.code === 'ECONNABORTED') {
        addPendingOrder(data);
        return { 
          data: { 
            ...data, 
            id: `offline-${Date.now()}`,
            _offline: true,
            items: data.items.map((item, idx) => ({
              ...item,
              id: `offline-item-${Date.now()}-${idx}`,
              status: 'pending'
            })),
            subtotal: data.items.reduce((sum, i) => sum + i.unit_price * i.quantity, 0),
            service_fee: 0,
            total: data.items.reduce((sum, i) => sum + i.unit_price * i.quantity, 0),
            is_closed: false,
            created_at: new Date().toISOString()
          },
          _offline: true 
        };
      }
      throw e;
    }
  },
  updateItemStatus: (orderId, itemId, status) => 
    api.put(`/orders/${orderId}/item/${itemId}/status`, { status }),
  cancelItem: (orderId, itemId, payload) =>
    api.patch(`/orders/${orderId}/item/${itemId}/cancel`, payload),
  close: (orderId, payments) => api.post(`/orders/${orderId}/close`, { payments }),
  // Cobrança no caixa: cortesia por quantidade, desconto por item, pagamento parcial e estorno.
  // payload da cortesia: { is_courtesy, quantity?, reason }
  courtesy: (orderId, itemId, payload) =>
    api.patch(`/orders/${orderId}/item/${itemId}/courtesy`, payload),
  // payload: { quantity?, type: 'value'|'percent', value, reason, admin_email?, admin_password? }
  discount: (orderId, itemId, payload) =>
    api.patch(`/orders/${orderId}/item/${itemId}/discount`, payload),
  removeDiscount: (orderId, itemId) => api.delete(`/orders/${orderId}/item/${itemId}/discount`),
  // payload: { payments: [{method, amount}], amount } ou { payments, items: [{item_id, quantity}] }
  partialPayment: (orderId, payload) => api.post(`/orders/${orderId}/partial-payments`, payload),
  // payload: { reason, admin_email?, admin_password? }
  reversePartial: (orderId, partialId, payload) =>
    api.post(`/orders/${orderId}/partial-payments/${partialId}/reverse`, payload),
};

// Promoções gerenciais (só admin cria/edita/desliga; "active" serve à tela de lançamento)
export const promotionsAPI = {
  list: () => api.get('/promotions'),
  active: (channel = 'salao') => api.get('/promotions/active', { params: { channel } }),
  create: (data) => api.post('/promotions', data),
  update: (id, data) => api.put(`/promotions/${id}`, data),
  setActive: (id, isActive) => api.patch(`/promotions/${id}/active`, { is_active: isActive }),
};

// Stock
export const stockAPI = {
  getAll: () => api.get('/stock'),
  create: (data) => api.post('/stock', data),
  update: (id, data) => api.put(`/stock/${id}`, data),
  getAlerts: () => api.get('/stock/alerts'),
};

// Cash Register
export const cashRegisterAPI = {
  getCurrent: () => api.get('/cash-register/current'),
  open: (data) => api.post('/cash-register/open', data),
  close: (data) => api.post('/cash-register/close', data),
  withdrawal: (data) => api.post('/cash-register/withdrawal', data),
  deposit: (data) => api.post('/cash-register/deposit', data),
};

// Invoices
export const invoicesAPI = {
  getAll: () => api.get('/invoices'),
  create: (data) => api.post('/invoices', data),
};

// Reports
export const reportsAPI = {
  getSales: (period) => api.get('/reports/sales', { params: { period } }),
  getProfit: (period) => api.get('/reports/profit', { params: { period } }),
  getSalesByTable: (period) => api.get('/reports/sales-by-table', { params: { period } }),
  // start/end: 'AAAA-MM-DD' (datas do restaurante, inclusive)
  getPromotions: (start, end) => api.get('/reports/promotions', { params: { start, end } }),
};

// Recipes (CMV)
export const recipesAPI = {
  getAll: () => api.get('/recipes'),
  getByProduct: (productId) => api.get(`/recipes/by-product/${productId}`),
  get: (id) => api.get(`/recipes/${id}`),
  create: (data) => api.post('/recipes', data),
  update: (id, data) => api.put(`/recipes/${id}`, data),
  delete: (id) => api.delete(`/recipes/${id}`),
};

// CMV
export const cmvAPI = {
  getProductCmv: (productId) => api.get(`/products/${productId}/cmv`),
  getReport: () => api.get('/cmv/report'),
};

// Productions
export const productionsAPI = {
  getAll: () => api.get('/productions'),
  create: (data) => api.post('/productions', data),
  getDashboard: () => api.get('/productions/dashboard'),
};

// Production Recipes (fórmulas de produção)
export const productionRecipesAPI = {
  getAll: () => api.get('/production-recipes'),
  getByStock: (stockId) => api.get(`/production-recipes/by-stock/${stockId}`),
  get: (id) => api.get(`/production-recipes/${id}`),
  create: (data) => api.post('/production-recipes', data),
  update: (id, data) => api.put(`/production-recipes/${id}`, data),
  delete: (id) => api.delete(`/production-recipes/${id}`),
};

// Integração NostFood (iFood / 99) e avisos do KDS
const NOSTFOOD = '/integrations/nostfood';
export const nostfoodAPI = {
  status: () => api.get(`${NOSTFOOD}/status`),
  simulate: (data) => api.post(`${NOSTFOOD}/simular`, data || {}),
  unlinked: () => api.get(`${NOSTFOOD}/produtos-sem-ligacao`),
  links: () => api.get(`${NOSTFOOD}/ligacoes`),
  link: (data) => api.post(`${NOSTFOOD}/ligar-produto`, data),
  losses: (params) => api.get(`${NOSTFOOD}/perdas`, { params }),
  deleteTests: () => api.delete(`${NOSTFOOD}/testes`),
  notReceived: (orderId, reason) => api.post(`${NOSTFOOD}/pedidos/${orderId}/nao-recebido`, { reason }),
};

export const kdsAPI = {
  getCancelled: () => api.get(`${NOSTFOOD}/kds/cancelados`),
  ackCancel: (orderId, station) =>
    api.post(`${NOSTFOOD}/pedidos/${orderId}/cancelamento/ciente`, { station }),
  ackObservation: (orderId, obsId, station) =>
    api.post(`/orders/${orderId}/observacao/${obsId}/ciente`, { station }),
};

// Listen for online event to sync
if (typeof window !== 'undefined') {
  window.addEventListener('online', async () => {
    console.log('Back online, syncing pending orders...');
    const result = await syncPendingOrders();
    if (result.synced > 0) {
      console.log(`Synced ${result.synced} orders`);
    }
  });
}

export default api;
