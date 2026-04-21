import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, UserCheck, UserX } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AuthUser } from "@/types/api";
import { authFetch, authFetchJson, authPostJson } from "@/services/api";

const USERS_KEY = ["users"];

function useUsers() {
  return useQuery({
    queryKey: USERS_KEY,
    queryFn: () => authFetchJson<AuthUser[]>("/api/v1/auth/users/"),
  });
}

function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; nombre: string; password: string; role: string }) =>
      authPostJson<AuthUser>("/api/v1/auth/users/", data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: USERS_KEY });
      toast.success("Usuario creado.");
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Error al crear usuario."),
  });
}

function useToggleActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      authFetch(`/api/v1/auth/users/${id}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active }),
      }).then((r) => { if (!r.ok) throw new Error("Error al actualizar usuario."); }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: USERS_KEY }),
    onError: (err) => toast.error(err instanceof Error ? err.message : "Error."),
  });
}

function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      authFetch(`/api/v1/auth/users/${id}/`, { method: "DELETE" }).then((r) => {
        if (!r.ok) throw new Error("Error al eliminar usuario.");
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: USERS_KEY });
      toast.success("Usuario eliminado.");
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Error."),
  });
}

const EMPTY_FORM = { email: "", nombre: "", password: "", role: "tecnico" };

export default function UserManagement() {
  const { data: users = [], isLoading } = useUsers();
  const createMut = useCreateUser();
  const toggleMut = useToggleActive();
  const deleteMut = useDeleteUser();

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    await createMut.mutateAsync(form);
    setForm(EMPTY_FORM);
    setShowForm(false);
  };

  return (
    <div className="w-full px-[36px] sm:px-[44px] lg:px-[52px] xl:px-[60px] 2xl:px-[400px] py-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Gestión de usuarios</h1>
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus className="w-4 h-4 mr-1" /> Nuevo usuario
        </Button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="border border-border rounded-lg p-4 space-y-3 bg-card">
          <h2 className="font-medium text-sm">Crear usuario</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="nu-nombre">Nombre</Label>
              <Input
                id="nu-nombre"
                value={form.nombre}
                onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))}
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="nu-email">Email</Label>
              <Input
                id="nu-email"
                type="email"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="nu-password">Contraseña</Label>
              <Input
                id="nu-password"
                type="password"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                required
                minLength={8}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="nu-role">Rol</Label>
              <select
                id="nu-role"
                value={form.role}
                onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="tecnico">Técnico</option>
                <option value="administrador">Administrador</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="outline" size="sm" onClick={() => setShowForm(false)}>
              Cancelar
            </Button>
            <Button type="submit" size="sm" disabled={createMut.isPending}>
              {createMut.isPending ? "Creando..." : "Crear"}
            </Button>
          </div>
        </form>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Cargando usuarios...</p>
      ) : (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Nombre</th>
                <th className="px-4 py-2 text-left font-medium">Email</th>
                <th className="px-4 py-2 text-left font-medium">Rol</th>
                <th className="px-4 py-2 text-left font-medium">Estado</th>
                <th className="px-4 py-2 text-left font-medium">Registro</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-border">
                  <td className="px-4 py-2">{u.nombre}</td>
                  <td className="px-4 py-2 text-muted-foreground">{u.email}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      u.role === "administrador"
                        ? "bg-amber-100 text-amber-700"
                        : "bg-blue-100 text-blue-700"
                    }`}>
                      {u.role === "administrador" ? "Admin" : "Técnico"}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <button
                      title={u.is_active ? "Desactivar" : "Activar"}
                      onClick={() => toggleMut.mutate({ id: u.id, is_active: !u.is_active })}
                      className="text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {u.is_active ? (
                        <UserCheck className="w-4 h-4 text-green-600" />
                      ) : (
                        <UserX className="w-4 h-4 text-destructive" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground text-xs">
                    {new Date(u.date_joined).toLocaleDateString("es-ES")}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      title="Eliminar"
                      onClick={() => {
                        if (confirm(`¿Eliminar a ${u.nombre}?`)) {
                          deleteMut.mutate(u.id);
                        }
                      }}
                      className="text-muted-foreground hover:text-destructive transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground text-sm">
                    No hay usuarios registrados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
