import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, GitBranch, Plus, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusTag } from "@/components/ui/StatusTag";
import type { FeatureModelNode, UVLPreviewActivationReport, UVLVersionSummary } from "@/types/api";
import { uvlApi } from "@/services/uvlApi";

// ── section definitions ───────────────────────────────────────────────────────

type RelationType = "MANDATORY" | "OPTIONAL" | "ALTERNATIVE" | "OR";

type AttrField = {
  key: string;
  label: string;
  type: "text" | "number" | "select";
  options?: string[];
  required?: boolean;
};

type SectionDef = {
  id: string;
  title: string;
  hint: string;
  parentName: string;
  relType: RelationType;
  leavesOnly: boolean;
  excludeNames?: Set<string>;
  attrFields: AttrField[];
};

const SECTIONS: SectionDef[] = [
  {
    id: "cultivo",
    title: "Cultivos",
    hint: "Grupo alternative — sólo uno seleccionable por configuración.",
    parentName: "Cultivo",
    relType: "ALTERNATIVE",
    leavesOnly: false,
    attrFields: [
      { key: "label", label: "Etiqueta", type: "text" },
      { key: "window_size", label: "Ventana (días)", type: "number", required: true },
      { key: "preferred_algorithm", label: "Algoritmo", type: "select", options: ["LSTM", "GradientBoosting"], required: true },
      { key: "min_samples", label: "Min muestras LSTM", type: "number", required: true },
      { key: "min_reject", label: "min_reject", type: "number", required: true },
      { key: "min_warn", label: "min_warn", type: "number", required: true },
      { key: "min_good", label: "min_good", type: "number", required: true },
    ],
  },
  {
    id: "tiposuelo",
    title: "Tipos de suelo",
    hint: "Grupo alternative — sólo uno seleccionable por configuración.",
    parentName: "TipoSuelo",
    relType: "ALTERNATIVE",
    leavesOnly: false,
    attrFields: [
      { key: "label", label: "Etiqueta", type: "text", required: true },
    ],
  },
  {
    id: "sensores",
    title: "Parámetros de entrada",
    hint: "Sensores opcionales. Dendrómetro, Humedad y Temperatura son fijos.",
    parentName: "ParametrosEntrada",
    relType: "OPTIONAL",
    leavesOnly: true,
    excludeNames: new Set(["TemperaturaAire"]),
    attrFields: [
      { key: "label", label: "Etiqueta", type: "text", required: true },
      { key: "csv_col", label: "Columna CSV", type: "text", required: true },
    ],
  },
  {
    id: "telemetria",
    title: "Datos de telemetría",
    hint: "Índices Sentinel-2. Añadir también la fórmula en telemetry_service.py.",
    parentName: "DatosTelemetria",
    relType: "OPTIONAL",
    leavesOnly: false,
    attrFields: [
      { key: "label", label: "Etiqueta", type: "text" },
      { key: "csv_col", label: "Columna CSV", type: "text", required: true },
    ],
  },
  {
    id: "objetivo",
    title: "Variable objetivo",
    hint: "Nombre del feature = nombre de columna CSV (convenio del sistema).",
    parentName: "VariableObjetivo",
    relType: "ALTERNATIVE",
    leavesOnly: false,
    attrFields: [
      { key: "label", label: "Etiqueta", type: "text" },
      { key: "quality_min", label: "R² mínimo", type: "number", required: true },
      { key: "quality_good", label: "R² bueno", type: "number", required: true },
    ],
  },
];

// ── tree helpers ──────────────────────────────────────────────────────────────

const _PREC: Record<string, number> = { IMPLIES: 0, OR: 1, AND: 2, NOT: 3, FEATURE: 4 };
type ASTNode = { op: string; name?: string; left?: ASTNode; right?: ASTNode };

function astToText(node: ASTNode, parentPrec = -1): string {
  if (node.op === "FEATURE") return node.name ?? "";
  if (node.op === "NOT") return `!${astToText(node.left!, _PREC.NOT)}`;
  const myPrec = _PREC[node.op] ?? 0;
  let expr = "";
  if (node.op === "IMPLIES") expr = `${astToText(node.left!, myPrec)} => ${astToText(node.right!, myPrec)}`;
  else if (node.op === "AND") expr = `${astToText(node.left!, myPrec)} & ${astToText(node.right!, myPrec)}`;
  else if (node.op === "OR") expr = `${astToText(node.left!, myPrec)} | ${astToText(node.right!, myPrec)}`;
  return myPrec < parentPrec ? `(${expr})` : expr;
}

function constraintsToText(constraints: FeatureModelNode["constraints"]): string {
  if (!constraints?.length) return "";
  return constraints.map(c => astToText(c.ast as ASTNode)).join("\n");
}

function findNodeByName(root: FeatureModelNode, name: string): FeatureModelNode | null {
  if (root.name === name) return root;
  for (const rel of root.relations) {
    for (const child of rel.children) {
      const r = findNodeByName(child, name);
      if (r) return r;
    }
  }
  return null;
}

function isLeafNode(node: FeatureModelNode): boolean {
  return node.relations.every(r => r.children.length === 0);
}

function getEditableLeaves(tree: FeatureModelNode, section: SectionDef): FeatureModelNode[] {
  const parent = findNodeByName(tree, section.parentName);
  if (!parent) return [];
  // Flamapy serialises each optional feature as its own single-child relation group,
  // so we must collect across ALL matching groups, not just the first one.
  let children = parent.relations
    .filter(r => r.type === section.relType)
    .flatMap(r => r.children);
  if (section.leavesOnly) children = children.filter(isLeafNode);
  if (section.excludeNames) children = children.filter(c => !section.excludeNames!.has(c.name));
  return children;
}

function applyToSection(
  tree: FeatureModelNode,
  section: SectionDef,
  updater: (editable: FeatureModelNode[]) => FeatureModelNode[],
): FeatureModelNode {
  function walk(node: FeatureModelNode): FeatureModelNode {
    if (node.name === section.parentName) {
      // Collect all children from every matching relation group
      const matchingChildren = node.relations
        .filter(r => r.type === section.relType)
        .flatMap(r => r.children);
      const locked = matchingChildren.filter(c =>
        (section.leavesOnly && !isLeafNode(c)) || section.excludeNames?.has(c.name),
      );
      const editable = matchingChildren.filter(c =>
        !(section.leavesOnly && !isLeafNode(c)) && !section.excludeNames?.has(c.name),
      );
      const combined = [...locked, ...updater(editable)];
      // Rebuild: keep non-matching groups, merge all matching into a single group
      const nonMatching = node.relations.filter(r => r.type !== section.relType);
      const merged = combined.length > 0 ? [{ type: section.relType, children: combined }] : [];
      return { ...node, relations: [...nonMatching, ...merged] };
    }
    return {
      ...node,
      relations: node.relations.map(rel => ({
        ...rel,
        children: rel.children.map(walk),
      })),
    };
  }
  return walk(tree);
}

// ── hooks ─────────────────────────────────────────────────────────────────────

const VERSIONS_KEY = ["uvl-versions"];

function useVersions() {
  return useQuery({ queryKey: VERSIONS_KEY, queryFn: uvlApi.listVersions });
}

function useVersionDetail(id: number | null) {
  return useQuery({
    queryKey: ["uvl-version", id],
    queryFn: () => uvlApi.getVersion(id!),
    enabled: id !== null,
  });
}

function useCreateVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: { name: string; description: string; tree: FeatureModelNode; constraintsText: string }) =>
      uvlApi.createVersion(p.name, p.description, p.tree, p.constraintsText),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: VERSIONS_KEY });
      toast.success("Versión creada correctamente.");
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Error al crear versión."),
  });
}

function useActivateVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, confirm }: { id: number; confirm: boolean }) =>
      uvlApi.activateVersion(id, confirm),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: VERSIONS_KEY });
      toast.success(data.detail);
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Error al activar versión."),
  });
}

function useDeleteVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => uvlApi.deleteVersion(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: VERSIONS_KEY });
      toast.success("Versión eliminada.");
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Error al eliminar versión."),
  });
}

// ── VersionCard ───────────────────────────────────────────────────────────────

function VersionCard({
  version, selected, onClick, onDelete,
}: {
  version: UVLVersionSummary; selected: boolean; onClick: () => void; onDelete: (id: number) => void;
}) {
  return (
    <div
      className={`group relative rounded-lg border transition-colors cursor-pointer ${
        selected ? "border-primary/40 bg-primary/5" : "border-transparent hover:border-border hover:bg-muted/40"
      }`}
      onClick={onClick}
    >
      <div className="px-3 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium text-sm truncate">{version.name}</span>
          <div className="flex items-center gap-1.5 shrink-0">
            {version.is_active && <StatusTag tone="success">Activa</StatusTag>}
            {!version.is_valid && <StatusTag tone="danger">Inválida</StatusTag>}
            {!version.is_active && (
              <button
                className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive p-0.5"
                title="Eliminar versión"
                onClick={e => {
                  e.stopPropagation();
                  if (confirm(`¿Eliminar versión "${version.name}"?`)) onDelete(version.id);
                }}
              >
                <Trash2 size={12} />
              </button>
            )}
          </div>
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          {new Date(version.created_at).toLocaleDateString("es-ES")}
          {version.author_username && ` · ${version.author_username}`}
        </div>
      </div>
    </div>
  );
}

// ── LeafRow ───────────────────────────────────────────────────────────────────

function LeafRow({
  leaf, section, editable, onUpdate, onDelete,
}: {
  leaf: FeatureModelNode; section: SectionDef; editable: boolean;
  onUpdate: (n: FeatureModelNode) => void; onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const attrs = (leaf.attributes ?? {}) as Record<string, string | number | boolean>;

  const summary = section.attrFields
    .filter(f => attrs[f.key] !== undefined && String(attrs[f.key]) !== "")
    .slice(0, 3)
    .map(f => `${f.label}: ${String(attrs[f.key])}`)
    .join(" · ");

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div
        className={`flex items-center gap-2 px-3 py-2 min-w-0 ${editable ? "cursor-pointer select-none hover:bg-muted/20" : ""}`}
        onClick={() => editable && setExpanded(e => !e)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-1.5 min-w-0">
            <span className="font-mono text-sm font-medium truncate">{leaf.name}</span>
            {attrs.label && String(attrs.label) !== leaf.name && (
              <span className="text-xs text-muted-foreground truncate shrink-0">— {String(attrs.label)}</span>
            )}
          </div>
          {summary && !expanded && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">{summary}</p>
          )}
        </div>
        {editable && (
          <div className="flex items-center gap-1 shrink-0" onClick={e => e.stopPropagation()}>
            <button
              className="text-muted-foreground hover:text-destructive p-0.5"
              title="Eliminar"
              onClick={() => { if (confirm(`¿Eliminar "${leaf.name}"?`)) onDelete(); }}
            >
              <Trash2 size={12} />
            </button>
          </div>
        )}
      </div>

      {editable && expanded && (
        <div className="border-t border-border bg-muted/20 px-3 py-2.5 space-y-2">
          <div className="flex items-center gap-2">
            <Label className="text-xs w-36 shrink-0 text-muted-foreground">Nombre (feature)</Label>
            <Input
              className="h-7 text-xs font-mono"
              value={leaf.name}
              onChange={e => onUpdate({ ...leaf, name: e.target.value })}
            />
          </div>
          {section.attrFields.map(field => (
            <div key={field.key} className="flex items-center gap-2">
              <Label className="text-xs w-36 shrink-0 text-muted-foreground">{field.label}</Label>
              {field.type === "select" ? (
                <select
                  className="h-7 text-xs border border-input rounded px-1.5 bg-background flex-1"
                  value={String(attrs[field.key] ?? field.options![0])}
                  onChange={e => onUpdate({ ...leaf, attributes: { ...attrs, [field.key]: e.target.value } })}
                >
                  {field.options!.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <Input
                  className="h-7 text-xs font-mono"
                  type={field.type === "number" ? "number" : "text"}
                  value={String(attrs[field.key] ?? "")}
                  onChange={e => onUpdate({
                    ...leaf,
                    attributes: {
                      ...attrs,
                      [field.key]: field.type === "number" ? Number(e.target.value) : e.target.value,
                    },
                  })}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── AddLeafForm ───────────────────────────────────────────────────────────────

function AddLeafForm({
  section, onAdd, onCancel,
}: {
  section: SectionDef; onAdd: (leaf: FeatureModelNode) => void; onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [vals, setVals] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of section.attrFields) init[f.key] = f.options?.[0] ?? "";
    return init;
  });

  function submit() {
    const n = name.trim();
    if (!n) { toast.error("Nombre obligatorio."); return; }
    const attrs: Record<string, string | number> = {};
    for (const f of section.attrFields) {
      const v = vals[f.key];
      if (v !== "" && v !== undefined) attrs[f.key] = f.type === "number" ? Number(v) : v;
    }
    onAdd({ name: n, relations: [], attributes: attrs });
  }

  return (
    <div className="border border-dashed border-primary/40 rounded-lg p-3 bg-primary/5 space-y-2 mt-2">
      <div className="flex items-center gap-2">
        <Label className="text-xs w-36 shrink-0 text-muted-foreground">Nombre (feature)</Label>
        <Input
          className="h-7 text-xs font-mono"
          placeholder="NombreFeature"
          value={name}
          autoFocus
          onChange={e => setName(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") submit(); if (e.key === "Escape") onCancel(); }}
        />
      </div>
      {section.attrFields.map(field => (
        <div key={field.key} className="flex items-center gap-2">
          <Label className="text-xs w-36 shrink-0 text-muted-foreground">{field.label}</Label>
          {field.type === "select" ? (
            <select
              className="h-7 text-xs border border-input rounded px-1.5 bg-background flex-1"
              value={vals[field.key] ?? ""}
              onChange={e => setVals(v => ({ ...v, [field.key]: e.target.value }))}
            >
              {field.options!.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <Input
              className="h-7 text-xs font-mono"
              type={field.type === "number" ? "number" : "text"}
              placeholder={field.required ? "requerido" : "opcional"}
              value={vals[field.key] ?? ""}
              onChange={e => setVals(v => ({ ...v, [field.key]: e.target.value }))}
            />
          )}
        </div>
      ))}
      <div className="flex justify-end gap-1.5 pt-1">
        <Button size="sm" variant="ghost" onClick={onCancel}><X size={12} className="mr-1" />Cancelar</Button>
        <Button size="sm" onClick={submit}><Check size={12} className="mr-1" />Añadir</Button>
      </div>
    </div>
  );
}

// ── LeafGroupPanel ────────────────────────────────────────────────────────────

function LeafGroupPanel({
  section, leaves, editable, onChange,
}: {
  section: SectionDef;
  leaves: FeatureModelNode[];
  editable: boolean;
  onChange?: (updater: (current: FeatureModelNode[]) => FeatureModelNode[]) => void;
}) {
  const [adding, setAdding] = useState(false);

  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{section.title}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{section.hint}</p>
        </div>
        {editable && !adding && (
          <Button size="sm" variant="outline" className="shrink-0" onClick={() => setAdding(true)}>
            <Plus size={12} className="mr-1" /> Añadir
          </Button>
        )}
      </div>

      <div className="space-y-1">
        {leaves.length === 0 && (
          <p className="text-xs text-muted-foreground italic py-1">Sin entradas.</p>
        )}
        {leaves.map((leaf, idx) => (
          <LeafRow
            key={`${leaf.name}-${idx}`}
            leaf={leaf}
            section={section}
            editable={editable}
            onUpdate={updated => onChange?.(arr => arr.map((l, i) => i === idx ? updated : l))}
            onDelete={() => onChange?.(arr => arr.filter((_, i) => i !== idx))}
          />
        ))}
      </div>

      {editable && adding && (
        <AddLeafForm
          section={section}
          onAdd={leaf => { onChange?.(arr => [...arr, leaf]); setAdding(false); }}
          onCancel={() => setAdding(false)}
        />
      )}
    </div>
  );
}

// ── ActivationModal ───────────────────────────────────────────────────────────

function ActivationModal({
  versionId, versionName, onClose,
}: {
  versionId: number; versionName: string; onClose: () => void;
}) {
  const [report, setReport] = useState<UVLPreviewActivationReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmText, setConfirmText] = useState("");
  const activateMut = useActivateVersion();

  useEffect(() => {
    uvlApi.previewActivation(versionId)
      .then(r => { setReport(r); setLoading(false); })
      .catch(() => setLoading(false));
  }, [versionId]);

  const hasAffected = (report?.affected.length ?? 0) > 0;
  const canActivate = !hasAffected || confirmText === "CONFIRMAR";

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-background border border-border rounded-xl max-w-lg w-full p-6 space-y-4">
        <h3 className="font-semibold text-lg">Activar versión: {versionName}</h3>

        {loading && <p className="text-sm text-muted-foreground">Calculando impacto...</p>}

        {!loading && report && (
          <>
            <p className="text-sm text-muted-foreground">
              Configuraciones guardadas: <strong>{report.total}</strong>
            </p>
            {hasAffected ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm text-amber-600">
                  <AlertTriangle size={14} />
                  <span>{report.affected.length} quedarán obsoletas:</span>
                </div>
                <div className="max-h-40 overflow-y-auto space-y-1 text-xs border border-border rounded p-2">
                  {report.affected.map(a => (
                    <div key={a.id} className="text-muted-foreground">
                      <span className="font-medium text-foreground">{a.nombre}</span> ({a.user}) — {a.reason}
                    </div>
                  ))}
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Escribe <strong>CONFIRMAR</strong> para continuar:</Label>
                  <Input
                    className="h-8 text-sm"
                    value={confirmText}
                    onChange={e => setConfirmText(e.target.value)}
                    placeholder="CONFIRMAR"
                  />
                </div>
              </div>
            ) : (
              <p className="text-sm text-green-600">Ninguna configuración se verá afectada.</p>
            )}
          </>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button
            disabled={loading || !canActivate || activateMut.isPending}
            onClick={() => activateMut.mutate({ id: versionId, confirm: hasAffected }, { onSuccess: onClose })}
          >
            {activateMut.isPending ? "Activando..." : "Activar versión"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function UvlEditor() {
  const { data: versions = [], isLoading } = useVersions();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [editTree, setEditTree] = useState<FeatureModelNode | null>(null);
  const [constraintsText, setConstraintsText] = useState("");
  const [draftName, setDraftName] = useState("");
  const [draftDesc, setDraftDesc] = useState("");
  const [activatingId, setActivatingId] = useState<number | null>(null);

  const { data: versionDetail } = useVersionDetail(selectedId);
  const createMut = useCreateVersion();
  const deleteMut = useDeleteVersion();
  const selectedVersion = versions.find(v => v.id === selectedId);

  function handleSelectVersion(id: number) {
    setSelectedId(id);
    setIsCreating(false);
    setEditTree(null);
  }

  function handleStartCreate() {
    if (versionDetail?.tree) {
      setEditTree(structuredClone(versionDetail.tree));
      setConstraintsText(constraintsToText(versionDetail.tree.constraints));
    } else {
      setEditTree(null);
      setConstraintsText("");
    }
    setDraftName(`Versión ${versions.length + 1}`);
    setDraftDesc("");
    setIsCreating(true);
  }

  function handleSectionChange(section: SectionDef) {
    return (updater: (leaves: FeatureModelNode[]) => FeatureModelNode[]) => {
      setEditTree(prev => prev ? applyToSection(prev, section, updater) : prev);
    };
  }

  function handleSave() {
    if (!editTree || !draftName.trim()) { toast.error("Árbol y nombre son obligatorios."); return; }
    createMut.mutate(
      { name: draftName.trim(), description: draftDesc.trim(), tree: editTree, constraintsText },
      { onSuccess: v => { setIsCreating(false); setSelectedId(v.id); } },
    );
  }

  // ── render helpers ──

  function renderSections(tree: FeatureModelNode, editable: boolean) {
    return (
      <div className="space-y-4">
        {/* Parcela: Cultivos + Tipos suelo side by side */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border border-border rounded-xl p-4">
          {SECTIONS.slice(0, 2).map(section => (
            <LeafGroupPanel
              key={section.id}
              section={section}
              leaves={getEditableLeaves(tree, section)}
              editable={editable}
              onChange={editable ? handleSectionChange(section) : undefined}
            />
          ))}
        </div>

        {/* Sensores, Telemetría, Objetivo */}
        {SECTIONS.slice(2).map(section => (
          <div key={section.id} className="border border-border rounded-xl p-4">
            <LeafGroupPanel
              section={section}
              leaves={getEditableLeaves(tree, section)}
              editable={editable}
              onChange={editable ? handleSectionChange(section) : undefined}
            />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-64px)] overflow-hidden">
      {/* sidebar */}
      <aside className="w-72 shrink-0 border-r border-border flex flex-col">
        <div className="p-4 border-b border-border">
          <div className="flex items-center gap-2 mb-3">
            <GitBranch size={16} className="text-primary" />
            <h2 className="font-semibold text-sm">Versiones UVL</h2>
          </div>
          <Button size="sm" className="w-full" onClick={handleStartCreate}>
            <Plus size={14} className="mr-1.5" /> Nueva versión
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {isLoading && <p className="text-xs text-muted-foreground text-center py-4">Cargando...</p>}
          {versions.map(v => (
            <VersionCard
              key={v.id}
              version={v}
              selected={v.id === selectedId && !isCreating}
              onClick={() => handleSelectVersion(v.id)}
              onDelete={id => deleteMut.mutate(id, {
                onSuccess: () => { if (selectedId === id) setSelectedId(null); },
              })}
            />
          ))}
        </div>
      </aside>

      {/* main */}
      <main className="flex-1 overflow-y-auto p-6">

        {/* create mode */}
        {isCreating && (
          <div className="max-w-3xl mx-auto space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-lg">Nueva versión</h2>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setIsCreating(false)}>Cancelar</Button>
                <Button onClick={handleSave} disabled={createMut.isPending}>
                  {createMut.isPending ? "Guardando..." : "Guardar versión"}
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Nombre *</Label>
                <Input value={draftName} onChange={e => setDraftName(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Descripción</Label>
                <Input value={draftDesc} onChange={e => setDraftDesc(e.target.value)} placeholder="Opcional" />
              </div>
            </div>

            {editTree ? (
              <>
                {renderSections(editTree, true)}

                <div className="space-y-1.5">
                  <Label className="text-xs">
                    Constraints
                    <span className="text-muted-foreground font-normal ml-1">
                      (una por línea · FeatureA =&gt; FeatureB &amp; FeatureC)
                    </span>
                  </Label>
                  <textarea
                    className="w-full font-mono text-xs border border-input rounded-md p-2.5 bg-background resize-y min-h-36 focus:outline-none focus:ring-1 focus:ring-ring"
                    value={constraintsText}
                    onChange={e => setConstraintsText(e.target.value)}
                    spellCheck={false}
                  />
                </div>
              </>
            ) : (
              <div className="border border-dashed border-border rounded-xl p-8 text-center text-sm text-muted-foreground">
                Selecciona una versión existente primero para basarte en ella.
              </div>
            )}
          </div>
        )}

        {/* version detail (read-only) */}
        {!isCreating && selectedVersion && (
          <div className="max-w-3xl mx-auto space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="font-semibold text-lg">{selectedVersion.name}</h2>
                  {selectedVersion.is_active && <StatusTag tone="success">Activa</StatusTag>}
                  {!selectedVersion.is_valid && <StatusTag tone="danger">Inválida</StatusTag>}
                </div>
                {selectedVersion.description && (
                  <p className="text-sm text-muted-foreground">{selectedVersion.description}</p>
                )}
                <p className="text-xs text-muted-foreground mt-1">
                  {new Date(selectedVersion.created_at).toLocaleString("es-ES")}
                  {selectedVersion.author_username && ` · por ${selectedVersion.author_username}`}
                  {" · "}<span className="font-mono">{selectedVersion.file_hash.slice(0, 8)}…</span>
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                {!selectedVersion.is_active && selectedVersion.is_valid && (
                  <Button onClick={() => setActivatingId(selectedVersion.id)}>Activar versión</Button>
                )}
                <Button variant="outline" onClick={handleStartCreate}>
                  {selectedVersion.is_active ? "Crear versión desde esta" : "Bifurcar"}
                </Button>
              </div>
            </div>

            {selectedVersion.validation_errors.length > 0 && (
              <div className="border border-destructive/30 bg-destructive/5 rounded-lg p-3 space-y-1">
                {selectedVersion.validation_errors.map((e, i) => (
                  <p key={i} className="text-xs text-destructive">{e}</p>
                ))}
              </div>
            )}

            {versionDetail?.tree ? (
              <>
                {renderSections(versionDetail.tree, false)}

                {versionDetail.tree.constraints && versionDetail.tree.constraints.length > 0 && (
                  <div className="space-y-1.5">
                    <h3 className="text-sm font-medium">Constraints</h3>
                    <pre className="font-mono text-xs border border-border rounded-md p-2.5 bg-muted/30 whitespace-pre-wrap">
                      {constraintsToText(versionDetail.tree.constraints)}
                    </pre>
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Cargando árbol...</p>
            )}
          </div>
        )}

        {/* empty state */}
        {!isCreating && !selectedVersion && (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
            Selecciona una versión o crea una nueva.
          </div>
        )}
      </main>

      {activatingId !== null && (
        <ActivationModal
          versionId={activatingId}
          versionName={versions.find(v => v.id === activatingId)?.name ?? ""}
          onClose={() => setActivatingId(null)}
        />
      )}
    </div>
  );
}
