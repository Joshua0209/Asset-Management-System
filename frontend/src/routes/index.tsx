import { Navigate, type RouteObject } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { LoginPage } from '@/pages/auth/LoginPage';
import { ManagerDashboardPage } from '@/pages/manager/DashboardPage';
import { ManagerAssetListPage } from '@/pages/manager/AssetListPage';
import { HolderDashboardPage } from '@/pages/holder/DashboardPage';

export const routes: RouteObject[] = [
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/manager',
    element: <AppLayout role="manager" />,
    children: [
      { index: true, element: <Navigate to="dashboard" replace /> },
      { path: 'dashboard', element: <ManagerDashboardPage /> },
      { path: 'assets', element: <ManagerAssetListPage /> },
    ],
  },
  {
    path: '/holder',
    element: <AppLayout role="holder" />,
    children: [
      { index: true, element: <Navigate to="dashboard" replace /> },
      { path: 'dashboard', element: <HolderDashboardPage /> },
    ],
  },
  {
    path: '/',
    element: <Navigate to="/login" replace />,
  },
  {
    path: '*',
    element: <Navigate to="/login" replace />,
  },
];
