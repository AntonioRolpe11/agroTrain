import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import Layout from "@/components/Layout";
import RequireAdmin from "@/components/RequireAdmin";
import RequireAuth from "@/components/RequireAuth";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { FeatureTreesProvider } from "@/contexts/FeatureTreesContext";
import { GeoProvider } from "@/lib/geoContext";
import ComoFunciona from "@/pages/ComoFunciona";
import DigitalSensorCreation from "@/pages/DigitalSensorCreation";
import GenerarValorModelo from "@/pages/GenerarValorModelo";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import MisModelos from "@/pages/MisModelos";
import NotFound from "@/pages/NotFound";
import Results from "@/pages/Results";
import UserManagement from "@/pages/UserManagement";
import UvlEditor from "@/pages/UvlEditor";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Sonner />
      <BrowserRouter>
        <AuthProvider>
          <GeoProvider>
            <FeatureTreesProvider initialTrees={[{ features: [] }]}>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route element={<RequireAuth />}>
                  <Route element={<Layout />}>
                    <Route path="/" element={<Landing />} />
                    <Route path="/como-funciona" element={<ComoFunciona />} />
                    <Route path="/creacion-sensor-digital" element={<DigitalSensorCreation />} />
                    <Route path="/validacion-modelo" element={<Results />} />
                    <Route path="/mis-modelos" element={<MisModelos />} />
                    <Route path="/mis-modelos/:modelId/generar-valor" element={<GenerarValorModelo />} />
                    <Route
                      path="/usuarios"
                      element={
                        <RequireAdmin>
                          <UserManagement />
                        </RequireAdmin>
                      }
                    />
                    <Route
                      path="/uvl-editor"
                      element={
                        <RequireAdmin>
                          <UvlEditor />
                        </RequireAdmin>
                      }
                    />
                    <Route path="*" element={<NotFound />} />
                  </Route>
                </Route>
              </Routes>
            </FeatureTreesProvider>
          </GeoProvider>
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
