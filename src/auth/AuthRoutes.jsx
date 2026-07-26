import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './useAuth.js';

export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return <div className="auth-loading" role="status">로그인 상태를 확인하고 있습니다.</div>;
  }
  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}

export function PublicOnlyRoute() {
  const { status } = useAuth();
  if (status === 'loading') {
    return <div className="auth-loading" role="status">로그인 상태를 확인하고 있습니다.</div>;
  }
  if (status === 'authenticated') return <Navigate to="/chat" replace />;
  return <Outlet />;
}
