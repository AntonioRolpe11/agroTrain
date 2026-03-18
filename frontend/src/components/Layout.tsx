import { Leaf, LogOut, Menu, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/contexts/AuthContext";

const NAV_ITEMS = [
  { path: "/", label: "Inicio" },
  { path: "/creacion-sensor-digital", label: "Creación sensor digital" },
  { path: "/validacion-modelo", label: "Validación del modelo" },
  { path: "/mis-modelos", label: "Mis modelos" },
  { path: "/arquitectura", label: "Arquitectura" },
];

export default function Layout() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, logout, isAdmin } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname]);

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-md border-b border-border">
        <div className="w-full px-[36px] sm:px-[44px] lg:px-[52px] xl:px-[60px] 2xl:px-[400px] flex items-center justify-between h-14">
          <Link to="/" className="flex items-center gap-2 text-olive font-semibold">
            <Leaf className="w-5 h-5" />
            <span className="font-serif text-lg">AgroTrain</span>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  pathname === item.path
                    ? "bg-primary/10 text-olive"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
              >
                {item.label}
              </Link>
            ))}
            {isAdmin && (
              <Link
                to="/usuarios"
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors flex items-center gap-1 ${
                  pathname === "/usuarios"
                    ? "bg-primary/10 text-olive"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
              >
                <Users className="w-3.5 h-3.5" />
                Usuarios
              </Link>
            )}
          </nav>

          <div className="hidden md:flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              {user?.nombre}
              {isAdmin && (
                <span className="ml-1 text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">
                  Admin
                </span>
              )}
            </span>
            <button
              onClick={handleLogout}
              title="Cerrar sesión"
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>

          <button className="md:hidden p-2" onClick={() => setMobileOpen(!mobileOpen)}>
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {mobileOpen && (
          <nav className="md:hidden border-t border-border bg-background p-4 flex flex-col gap-2">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setMobileOpen(false)}
                className={`px-3 py-2 rounded-md text-sm font-medium ${
                  pathname === item.path ? "bg-primary/10 text-olive" : "text-muted-foreground"
                }`}
              >
                {item.label}
              </Link>
            ))}
            {isAdmin && (
              <Link
                to="/usuarios"
                onClick={() => setMobileOpen(false)}
                className="px-3 py-2 rounded-md text-sm font-medium text-muted-foreground flex items-center gap-2"
              >
                <Users className="w-4 h-4" /> Usuarios
              </Link>
            )}
            <button
              onClick={() => { setMobileOpen(false); handleLogout(); }}
              className="px-3 py-2 rounded-md text-sm font-medium text-muted-foreground flex items-center gap-2 text-left"
            >
              <LogOut className="w-4 h-4" /> Cerrar sesión ({user?.nombre})
            </button>
          </nav>
        )}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-border bg-card">
        <div className="w-full px-[36px] py-6 text-center text-xs text-muted-foreground sm:px-[44px] lg:px-[52px] xl:px-[60px] 2xl:px-[68px]">
          TFG · Configurador de sensores virtuales basado en UVL/Flamapy
        </div>
      </footer>
    </div>
  );
}
