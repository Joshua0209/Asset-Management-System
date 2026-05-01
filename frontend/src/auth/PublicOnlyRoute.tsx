import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";

/**
 * Inverse of ProtectedRoute: pages that should not be visible once the user
 * is logged in (login, register). Authenticated visitors are bounced to "/",
 * which then resolves to the role-specific landing.
 */
export const PublicOnlyRoute: React.FC = () => {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) return <Navigate to="/" replace />;
  return <Outlet />;
};
