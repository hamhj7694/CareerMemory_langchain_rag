import { Navigate, createBrowserRouter } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout.jsx';
import { DocumentPage } from './pages/DocumentPage.jsx';
import { ChatPage } from './pages/ChatPage.jsx';
import { JobDetailPage } from './pages/JobDetailPage.jsx';
import { JobsPage } from './pages/JobsPage.jsx';
import { MemoryDetailPage } from './pages/MemoryDetailPage.jsx';
import { MemoryManagerPage } from './pages/MemoryManagerPage.jsx';
import { NotFoundPage } from './pages/NotFoundPage.jsx';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'chat/:conversationId', element: <ChatPage /> },
      { path: 'memory', element: <MemoryManagerPage /> },
      { path: 'memory/:experienceId', element: <MemoryDetailPage /> },
      { path: 'jobs', element: <JobsPage /> },
      { path: 'jobs/:jobId', element: <JobDetailPage /> },
      { path: 'documents/:documentId', element: <DocumentPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
