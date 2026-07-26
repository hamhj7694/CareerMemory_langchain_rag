import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { router } from './router.jsx';
import { AuthProvider } from './auth/AuthContext.jsx';
import { getCanonicalDevelopmentUrl } from './auth/developmentHost.js';
import './styles/global.css';

const canonicalUrl = import.meta.env.DEV
  ? getCanonicalDevelopmentUrl(
      window.location.href,
      import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
    )
  : null;

if (canonicalUrl) {
  // 로그인 쿠키가 저장된 localhost로 경로와 검색 조건을 유지해 이동한다.
  window.location.replace(canonicalUrl);
} else {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </StrictMode>,
  );
}
