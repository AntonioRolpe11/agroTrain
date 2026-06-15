import { type ReactNode } from "react";
import { MapPinned } from "lucide-react";

import { FeatureNode } from "@/components/feature-model/FeatureNode";
import { HelpTip } from "@/components/ui/help-tip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useFeatureModelQuery, useMunicipiosQuery, useProvinciasQuery } from "@/hooks/useConfiguratorApi";
import { useGeo } from "@/hooks/useGeo";
import { FEATURE_HELP } from "@/lib/featureHelp";
import { getNode } from "@/utils/featureModel";

const selectClassName =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

interface ParcelDataCardProps {
  footer?: ReactNode;
  serverErrors?: string[];
}

export function ParcelDataCard({ footer, serverErrors = [] }: ParcelDataCardProps) {
  const { geo, patchGeo } = useGeo();
  const provinciasQuery = useProvinciasQuery();
  const municipiosQuery = useMunicipiosQuery(geo.provinciaId);
  const featureModelQuery = useFeatureModelQuery();

  const provincias = provinciasQuery.data ?? [];
  const municipios = municipiosQuery.data ?? [];
  const loadingProvincias = provinciasQuery.isPending;
  const loadingMunicipios = Boolean(geo.provinciaId) && municipiosQuery.isPending;

  const catalogError =
    provinciasQuery.error instanceof Error
      ? provinciasQuery.error.message
      : municipiosQuery.error instanceof Error
        ? municipiosQuery.error.message
        : null;

  const model = featureModelQuery.data ?? null;
  const tratamientoNode = model ? getNode(model, "Tratamiento") : null;
  const tipoSueloNode = model ? getNode(model, "TipoSuelo") : null;

  return (
    <div className="config-block animate-reveal-up" style={{ animationDelay: "155ms" }}>
      <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
        <MapPinned className="h-5 w-5 text-data-blue" /> Datos de la parcela
      </h2>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="parcela-nombre">Nombre de parcela</Label>
          <Input
            id="parcela-nombre"
            placeholder="Ej: Finca Los Cerros"
            value={geo.nombre}
            onChange={(e) => patchGeo({ nombre: e.target.value })}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="parcela-provincia">Provincia</Label>
          <select
            id="parcela-provincia"
            className={selectClassName}
            value={geo.provinciaId ?? ""}
            disabled={loadingProvincias}
            onChange={(e) => {
              const id = e.target.value || null;
              const found = provincias.find((p) => p.id === id) ?? null;
              patchGeo({
                provinciaId: id,
                provinciaNombre: found?.nombre ?? null,
                municipioId: null,
                municipioNombre: null,
                punto: null,
              });
            }}
          >
            <option value="">{loadingProvincias ? "Cargando provincias..." : "Selecciona una provincia"}</option>
            {provincias.map((p) => (
              <option key={p.id} value={p.id}>{p.nombre}</option>
            ))}
          </select>
        </div>

        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="parcela-municipio">Municipio</Label>
          <select
            id="parcela-municipio"
            key={geo.provinciaId ?? "sin-provincia"}
            className={selectClassName}
            value={geo.municipioId ?? ""}
            disabled={!geo.provinciaId || loadingMunicipios}
            onChange={(e) => {
              const id = e.target.value || null;
              const found = municipios.find((m) => m.id === id) ?? null;
              patchGeo({ municipioId: id, municipioNombre: found?.nombre ?? null, punto: null });
            }}
          >
            <option value="">
              {!geo.provinciaId
                ? "Selecciona primero una provincia"
                : loadingMunicipios
                  ? "Cargando municipios..."
                  : "Selecciona un municipio"}
            </option>
            {municipios.map((m) => (
              <option key={m.id} value={m.id}>{m.nombre}</option>
            ))}
          </select>
        </div>
      </div>

      {catalogError && <p className="mt-4 text-sm text-destructive">{catalogError}</p>}

      {(tratamientoNode || tipoSueloNode) && (
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          <div>
            <div className="mb-2 flex items-center gap-1.5">
              <Label className="block text-sm font-semibold">Tratamiento de riego</Label>
              <HelpTip text={FEATURE_HELP.Tratamiento} />
            </div>
            {tratamientoNode && <FeatureNode node={tratamientoNode} index={0} />}
          </div>
          <div>
            <div className="mb-2 flex items-center gap-1.5">
              <Label className="block text-sm font-semibold">Tipo de suelo</Label>
              <HelpTip text={FEATURE_HELP.TipoSuelo} />
            </div>
            {tipoSueloNode && <FeatureNode node={tipoSueloNode} index={0} />}
          </div>
        </div>
      )}

      {serverErrors.length > 0 && (
        <div className="mt-4 rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="mb-2 font-medium">Revisa este bloque antes de continuar</p>
          <ul className="list-disc space-y-1 pl-5">
            {serverErrors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      {footer && <div className="mt-4 flex justify-end border-t border-border/60 pt-4">{footer}</div>}
    </div>
  );
}
