import React, { useState } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import MainLayout from './components/layout/MainLayout';
import Dashboard from './pages/Dashboard';
import AssetList from './pages/AssetList';
import Reviews from './pages/Reviews';
import SubmitRepairRequest from './pages/SubmitRepairRequest';

// Initialize i18n
import './i18n';

const RootLayout: React.FC = () => {
  const [isDarkMode, setIsDarkMode] = useState(false);

  const toggleTheme = () => {
    setIsDarkMode(!isDarkMode);
  };

  return (
    <ConfigProvider
      theme={{
        algorithm: isDarkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: '#1677ff',
        },
      }}
    >
      <MainLayout isDarkMode={isDarkMode} toggleTheme={toggleTheme} />
    </ConfigProvider>
  );
};

const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      {
        index: true,
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
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
