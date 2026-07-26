import { apiConfig } from './config.js';
import { createHttpAdapter } from './adapters/httpAdapter.js';

const http = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  timeoutMs: apiConfig.timeoutMs,
});

export const authApi = {
  register(input) {
    return http.request({
      path: '/api/v2/auth/register',
      method: 'POST',
      body: input,
    });
  },
  login(input) {
    return http.request({
      path: '/api/v2/auth/login',
      method: 'POST',
      body: input,
    });
  },
  logout() {
    return http.request({
      path: '/api/v2/auth/logout',
      method: 'POST',
    });
  },
  setUsername(input) {
    return http.request({
      path: '/api/v2/auth/username',
      method: 'PUT',
      body: input,
    });
  },
  updateProfile(input) {
    return http.request({
      path: '/api/v2/auth/profile',
      method: 'PUT',
      body: input,
    });
  },
  findUsername(email) {
    return http.request({
      path: '/api/v2/auth/username/find',
      method: 'POST',
      body: { email },
    });
  },
  me() {
    return http.request({ path: '/api/v2/auth/me' });
  },
  setRecoveryQuestion(input) {
    return http.request({
      path: '/api/v2/auth/recovery-question',
      method: 'PUT',
      body: input,
    });
  },
  changePassword(input) {
    return http.request({
      path: '/api/v2/auth/password',
      method: 'PUT',
      body: input,
    });
  },
  recoverPassword(input) {
    return http.request({
      path: '/api/v2/auth/password/recover',
      method: 'POST',
      body: input,
    });
  },
};
