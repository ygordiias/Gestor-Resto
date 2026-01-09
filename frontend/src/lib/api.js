import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_URL = `${BACKEND_URL}/api`;

// Create axios instance with default config
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth
export const authAPI = {
  login: (data) => api.post('/auth/login', data),
  register: (data) => api.post('/auth/register', data),
  getMe: () => api.get('/auth/me'),
};

// Users
export const usersAPI = {
  getAll: () => api.get('/users'),
  create: (data) => api.post('/users', data),
  update: (id, data) => api.put(`/users/${id}`, data),
  delete: (id) => api.delete(`/users/${id}`),
};

// Categories
export const categoriesAPI = {
  getAll: () => api.get('/categories'),
  create: (data) => api.post('/categories', data),
  update: (id, data) => api.put(`/categories/${id}`, data),
  delete: (id) => api.delete(`/categories/${id}`),
};

// Products
export const productsAPI = {
  getAll: () => api.get('/products'),
  get: (id) => api.get(`/products/${id}`),
  create: (data) => api.post('/products', data),
  update: (id, data) => api.put(`/products/${id}`, data),
  delete: (id) => api.delete(`/products/${id}`),
};

// Tables
export const tablesAPI = {
  getAll: () => api.get('/tables'),
  create: (data) => api.post('/tables', data),
  update: (id, data) => api.put(`/tables/${id}`, data),
  delete: (id) => api.delete(`/tables/${id}`),
};

// Orders
export const ordersAPI = {
  getAll: (params) => api.get('/orders', { params }),
  getOpen: () => api.get('/orders/open'),
  get: (id) => api.get(`/orders/${id}`),
  getByTable: (tableId) => api.get(`/orders/table/${tableId}`),
  create: (data) => api.post('/orders', data),
  updateItemStatus: (orderId, itemId, status) => 
    api.put(`/orders/${orderId}/item/${itemId}/status`, { status }),
  close: (orderId, payments) => api.post(`/orders/${orderId}/close`, { payments }),
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
};

// Setup
export const setupAPI = {
  seed: () => api.post('/setup/seed'),
};

export default api;
