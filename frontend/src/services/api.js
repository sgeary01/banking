import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({ baseURL: API_BASE });

// Attach JWT token on every request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Auth ───────────────────────────────────────────────────────────────────────
export const login = (email, password) => {
  const form = new URLSearchParams();
  form.append('username', email);
  form.append('password', password);
  return api.post('/auth/login', form, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
};

export const register = (email, password, customerId) =>
  api.post('/auth/register', { email, password, customer_id: customerId });

// ── Customers ──────────────────────────────────────────────────────────────────
export const listCustomers = (skip = 0, limit = 50) =>
  api.get('/customers', { params: { skip, limit } });

export const getCustomer = id => api.get(`/customers/${id}`);

export const createCustomer = data => api.post('/customers', data);

// ── Accounts ───────────────────────────────────────────────────────────────────
export const getAccount = id => api.get(`/accounts/${id}`);

export const getCustomerAccounts = customerId =>
  api.get(`/accounts/customer/${customerId}`);

export const createAccount = data => api.post('/accounts', data);

// ── Transactions ───────────────────────────────────────────────────────────────
export const deposit = data => api.post('/transactions/deposit', data);

export const withdraw = data => api.post('/transactions/withdraw', data);

export const transfer = data => api.post('/transactions/transfer', data);

export const getAccountTransactions = (accountId, limit = 20) =>
  api.get(`/transactions/account/${accountId}`, { params: { limit } });

// ── Fraud ──────────────────────────────────────────────────────────────────────
export const getFraudAlerts = (status, limit = 50) =>
  api.get('/fraud/alerts', { params: { status, limit } });

// ── Reports ────────────────────────────────────────────────────────────────────
export const getAccountStatement = (accountId, limit = 50) =>
  api.get(`/reports/account/${accountId}/statement`, { params: { limit } });

export const getCustomerOverview = customerId =>
  api.get(`/reports/customer/${customerId}/overview`);

// ── Chaos ──────────────────────────────────────────────────────────────────────
export const getChaosScenarios = () => api.get('/chaos/scenarios');

export const triggerScenario = (name, accountIds) =>
  api.post(`/chaos/scenarios/${name}/trigger`, { account_ids: accountIds });

export const clearAllChaos = () => api.post('/chaos/scenarios/clear');

export const injectChaos = config => api.post('/chaos/inject', config);

export const generateLoad = (accountIds, count, highValue) =>
  api.post('/chaos/load/transactions', accountIds, {
    params: { count, high_value: highValue },
  });

export default api;
