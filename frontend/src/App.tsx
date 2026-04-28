import React from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import MainLayout from './components/layout/MainLayout';
import Dashboard from './pages/Dashboard';
import AssetList from './pages/AssetList';
import Reviews from './pages/Reviews';
import SubmitRepairRequest from './pages/SubmitRepairRequest';
import Login from './pages/auth/Login';
import Register from './pages/auth/Register';
import PasswordResetRequest from './pages/auth/PasswordResetRequest';
import PasswordResetConfirm from './pages/auth/PasswordResetConfirm';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/auth/ProtectedRoute';
import PublicRoute from './components/auth/PublicRoute';

import { ThemeProvider } from './contexts/ThemeContext';
import PublicLayout from './components/layout/PublicLayout';

// Initialize i18n
import './i18n';

const RootLayout: React.FC = () => {
  return <MainLayout />;
};

const router = createBrowserRouter([
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <RootLayout />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: <Navigate to="/dashboard" replace />,
      },
      {
        path: 'dashboard',
        element: <Dashboard />,
      },
      {
        path: 'assets',
        element: <AssetList />,
      },
      {
        path: 'reviews',
        element: <Reviews />,
      },
      {
        path: 'repairs/new',
        element: <SubmitRepairRequest />,
      },
    ],
  },
  {
    path: '/auth',
    element: <PublicLayout />,
    children: [
      {
        path: 'login',
        element: (
          <PublicRoute>
            <Login />
          </PublicRoute>
        ),
      },
      {
        path: 'register',
        element: (
          <PublicRoute>
            <Register />
          </PublicRoute>
        ),
      },
      {
        path: 'password-reset',
        element: (
          <PublicRoute>
            <PasswordResetRequest />
          </PublicRoute>
        ),
      },
      {
        path: 'password-reset/confirm',
        element: (
          <PublicRoute>
            <PasswordResetConfirm />
          </PublicRoute>
        ),
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);

function App() {
  return (
    <AuthProvider>
      <ThemeProvider>
        <RouterProvider router={router} />
      </ThemeProvider>
    </AuthProvider>
  );
}

export default App;
