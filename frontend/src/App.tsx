import React, { createContext, useContext, useMemo, useState } from "react";
import {
  Outlet,
  RouterProvider,
  createBrowserRouter,
  type RouteObject,
} from "react-router-dom";
import { ConfigProvider, theme } from "antd";
import MainLayout from "./components/layout/MainLayout";
import Dashboard from "./pages/Dashboard";
import AssetList from "./pages/AssetList";
import Reviews from "./pages/Reviews";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Forbidden from "./pages/Forbidden";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import RoleLandingRedirect from "./auth/RoleLandingRedirect";

// Initialize i18n
import "./i18n";

interface ThemeModeValue {
  isDarkMode: boolean;
  toggleTheme: () => void;
}

// Standalone React context — using useOutletContext breaks when an
// intermediate <Outlet/> (e.g. ProtectedRoute) doesn't forward the value.
const ThemeModeContext = createContext<ThemeModeValue | null>(null);

function useThemeMode(): ThemeModeValue {
  const ctx = useContext(ThemeModeContext);
  if (!ctx) throw new Error("useThemeMode must be used within ThemeModeContext");
  return ctx;
}

const RootProviders: React.FC = () => {
  const [isDarkMode, setIsDarkMode] = useState(false);
  const themeValue = useMemo<ThemeModeValue>(
    () => ({ isDarkMode, toggleTheme: () => setIsDarkMode((v) => !v) }),
    [isDarkMode],
  );

  return (
    <ConfigProvider
      theme={{
        algorithm: isDarkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: { colorPrimary: "#1677ff" },
      }}
    >
      <ThemeModeContext.Provider value={themeValue}>
        <AuthProvider>
          <Outlet />
        </AuthProvider>
      </ThemeModeContext.Provider>
    </ConfigProvider>
  );
};

const AppShell: React.FC = () => {
  const { isDarkMode, toggleTheme } = useThemeMode();
  return <MainLayout isDarkMode={isDarkMode} toggleTheme={toggleTheme} />;
};

export const routes: RouteObject[] = [
  {
    element: <RootProviders />,
    children: [
      { path: "/auth/login", element: <Login /> },
      { path: "/auth/register", element: <Register /> },
      {
        element: <ProtectedRoute />,
        children: [
          {
            element: <AppShell />,
            children: [
              { index: true, element: <RoleLandingRedirect /> },
              { path: "forbidden", element: <Forbidden /> },
              { path: "assets", element: <AssetList /> },
              {
                element: <ProtectedRoute allowedRoles={["manager"]} />,
                children: [
                  { path: "dashboard", element: <Dashboard /> },
                  { path: "reviews", element: <Reviews /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
];

const router = createBrowserRouter(routes);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
