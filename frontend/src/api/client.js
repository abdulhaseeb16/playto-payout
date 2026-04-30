import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const api = axios.create({ baseURL: BASE_URL });

export const getApiIndex = () => api.get('/');

export const getDashboard = (merchantId) =>
  api.get(`/merchants/${merchantId}/dashboard/`);

export const createPayout = (merchantId, payload) =>
  api.post(`/merchants/${merchantId}/payouts/`, payload, {
    headers: { 'Idempotency-Key': uuidv4() },
    // Fresh UUID per submit — never reuse across form submissions
  });

export const getPayout = (merchantId, payoutId) =>
  api.get(`/merchants/${merchantId}/payouts/${payoutId}/`);
