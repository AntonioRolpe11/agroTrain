import { Navigate } from "react-router-dom";

import { useAuth } from "@/contexts/AuthContext";

export default function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAuth();
  return isAdmin ? <>{children}</> : <Navigate to="/" replace />;
}
