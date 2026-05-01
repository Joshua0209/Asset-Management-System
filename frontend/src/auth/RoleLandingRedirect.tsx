import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";

const RoleLandingRedirect: React.FC = () => {
  const { user } = useAuth();
  if (user?.role === "manager") return <Navigate to="/dashboard" replace />;
  if (user?.role === "holder") return <Navigate to="/assets" replace />;
  return <Navigate to="/forbidden" replace />;
};

export default RoleLandingRedirect;
