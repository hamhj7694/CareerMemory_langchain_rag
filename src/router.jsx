import { Navigate, createBrowserRouter } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout.jsx';
import { DocumentPage } from './pages/DocumentPage.jsx';
import { ChatPage } from './pages/ChatPage.jsx';
import { JobDetailPage } from './pages/JobDetailPage.jsx';
import { JobsPage } from './pages/JobsPage.jsx';
import { MemoryDetailPage } from './pages/MemoryDetailPage.jsx';
import { MemoryManagerPage } from './pages/MemoryManagerPage.jsx';
import { ExperienceTrashPage } from './pages/ExperienceTrashPage.jsx';
import { NotFoundPage } from './pages/NotFoundPage.jsx';
import { LoginPage } from './pages/LoginPage.jsx';
import { RegisterPage } from './pages/RegisterPage.jsx';
import { AccountRecoveryPage } from './pages/AccountRecoveryPage.jsx';
import { AccountPage } from './pages/AccountPage.jsx';
import { FindUsernamePage } from './pages/FindUsernamePage.jsx';
import { ProtectedRoute, PublicOnlyRoute } from './auth/AuthRoutes.jsx';

export const router = createBrowserRouter([
  {
    element: <PublicOnlyRoute />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
      { path: '/find-username', element: <FindUsernamePage /> },
      { path: '/forgot-password', element: <AccountRecoveryPage /> },
    ],
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        path: '/',
        element: <AppLayout />,
        children: [
          { index: true, element: <Navigate to="/chat" replace /> },
          { path: 'chat', element: <ChatPage /> },
          { path: 'chat/:conversationId', element: <ChatPage /> },
          { path: 'memory', element: <MemoryManagerPage /> },
          { path: 'memory/new', element: <MemoryDetailPage /> },
          { path: 'memory/trash', element: <ExperienceTrashPage /> },
          { path: 'memory/:experienceId', element: <MemoryDetailPage /> },
          { path: 'jobs', element: <JobsPage /> },
          { path: 'jobs/:jobId', element: <JobDetailPage /> },
          { path: 'documents/:documentId', element: <DocumentPage /> },
          { path: 'account', element: <AccountPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
