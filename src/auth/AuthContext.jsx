import { useEffect, useMemo, useState } from 'react';
import { authApi } from '../api/authApi.js';
import {
  clearCsrfToken,
  clearCurrentUserId,
  setCsrfToken,
  setCurrentUserId,
} from './authSession.js';
import { AuthContext } from './authContext.js';
import { resetMockV2Store } from '../api/v2/mockV2Store.js';

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading');
  const [user, setUser] = useState(null);

  const applyAuthResponse = (response) => {
    resetMockV2Store();
    setCsrfToken(response.csrf_token);
    setCurrentUserId(response.user.id);
    setUser(response.user);
    setStatus('authenticated');
    return response.user;
  };

  useEffect(() => {
    let active = true;
    authApi.me()
      .then((response) => {
        if (active) applyAuthResponse(response);
      })
      .catch(() => {
        if (!active) return;
        clearCsrfToken();
        clearCurrentUserId();
        setUser(null);
        setStatus('anonymous');
      });
    return () => { active = false; };
  }, []);

  const value = useMemo(() => ({
    status,
    user,
    async login(input) {
      return applyAuthResponse(await authApi.login(input));
    },
    async register(input) {
      return applyAuthResponse(await authApi.register(input));
    },
    async setUsername(input) {
      return applyAuthResponse(await authApi.setUsername(input));
    },
    async updateProfile(input) {
      return applyAuthResponse(await authApi.updateProfile(input));
    },
    async logout() {
      await authApi.logout();
      resetMockV2Store();
      clearCsrfToken();
      clearCurrentUserId();
      setUser(null);
      setStatus('anonymous');
    },
  }), [status, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
