import { useCallback, useEffect, useRef, useState } from "react";
import L from "leaflet";
import { Map, MapPin, X } from "lucide-react";
import { MapContainer, Pane, TileLayer, WMSTileLayer, useMap, useMapEvents } from "react-leaflet";

import { useMunicipioViewportQuery } from "@/hooks/useConfiguratorApi";
import { useGeo } from "@/hooks/useGeo";
import type { ParcelBoundingBox } from "@/types/config";
import { Button } from "@/components/ui/button";

interface SigpacSource {
  url: string;
  layers: string;
  version: string;
}

const SPAIN_CENTER: L.LatLngExpression = [40.2, -3.7];
const DEFAULT_ZOOM = 6;
const MUNICIPIO_PADDING: L.PointTuple = [32, 32];
const SIGPAC_SOURCES: SigpacSource[] = [
  { url: "https://sigpac-hubcloud.es/wms", layers: "AU.Sigpac:recinto", version: "1.3.0" },
  { url: "https://wms.mapa.gob.es/sigpac/wms", layers: "PARCELA,RECINTO", version: "1.3.0" },
  { url: "https://wms.mapama.gob.es/wms/wms.aspx", layers: "PARCELA,RECINTO", version: "1.3.0" },
];

const treeIcon = L.divIcon({
  className: "",
  html: `<div style="
    width: 32px; height: 32px;
    background: #16a34a;
    border: 3px solid white;
    border-radius: 50% 50% 50% 0;
    transform: rotate(-45deg);
    box-shadow: 0 2px 6px rgba(0,0,0,0.4);
  "></div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 32],
});

function bboxToLeafletBounds(bbox: ParcelBoundingBox): L.LatLngBoundsExpression {
  return [[bbox[1], bbox[0]], [bbox[3], bbox[2]]];
}

function MapSizeSynchronizer() {
  const map = useMap();
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => { map.invalidateSize(); });
    return () => { window.cancelAnimationFrame(frame); };
  }, [map]);
  return null;
}

function PointPlacementController() {
  const map = useMap();
  const { geo, patchGeo } = useGeo();
  const markerRef = useRef<L.Marker | null>(null);
  const canPlace = Boolean(geo.provinciaId && geo.municipioId);

  const municipioViewportQuery = useMunicipioViewportQuery(
    geo.provinciaId,
    geo.municipioId,
    !geo.punto,
  );
  const municipioViewportBbox = !geo.punto && municipioViewportQuery.data?.found
    ? municipioViewportQuery.data.bbox
    : null;

  const savePoint = useCallback(
    (lat: number, lng: number) => { patchGeo({ punto: { lat, lng } }); },
    [patchGeo],
  );

  const placeMarker = useCallback(
    (latlng: L.LatLng) => {
      if (markerRef.current) {
        markerRef.current.setLatLng(latlng);
      } else {
        const marker = L.marker(latlng, { icon: treeIcon, draggable: true });
        marker.on("dragend", () => {
          const pos = marker.getLatLng();
          savePoint(pos.lat, pos.lng);
        });
        marker.addTo(map);
        markerRef.current = marker;
      }
      savePoint(latlng.lat, latlng.lng);
    },
    [map, savePoint],
  );

  useMapEvents({
    click(e) { if (canPlace) placeMarker(e.latlng); },
  });

  useEffect(() => {
    if (!geo.punto) {
      if (markerRef.current) { map.removeLayer(markerRef.current); markerRef.current = null; }
      return;
    }
    const latlng = L.latLng(geo.punto.lat, geo.punto.lng);
    if (markerRef.current) {
      markerRef.current.setLatLng(latlng);
    } else {
      const marker = L.marker(latlng, { icon: treeIcon, draggable: true });
      marker.on("dragend", () => { const pos = marker.getLatLng(); savePoint(pos.lat, pos.lng); });
      marker.addTo(map);
      markerRef.current = marker;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geo.punto?.lat, geo.punto?.lng]);

  useEffect(() => {
    if (geo.punto) { map.setView([geo.punto.lat, geo.punto.lng], Math.max(map.getZoom(), 17)); return; }
    if (municipioViewportBbox) { map.fitBounds(bboxToLeafletBounds(municipioViewportBbox), { padding: MUNICIPIO_PADDING }); return; }
    if (!markerRef.current) { map.setView(SPAIN_CENTER, DEFAULT_ZOOM); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, municipioViewportBbox, geo.punto]);

  return null;
}

function MapDisabledOverlay() {
  return (
    <div className="absolute inset-0 z-[500] flex items-center justify-center bg-background/80 p-6 text-center backdrop-blur-[1px]">
      <div className="max-w-md space-y-3">
        <MapPin className="mx-auto h-10 w-10 text-muted-foreground" />
        <div>
          <p className="font-medium">Selecciona provincia y municipio antes de colocar el punto</p>
          <p className="mt-1 text-sm text-muted-foreground">
            El mapa se centrará en tu municipio para que puedas colocar el punto exactamente sobre el árbol.
          </p>
        </div>
      </div>
    </div>
  );
}

export function ParcelMap() {
  const { geo, patchGeo } = useGeo();
  const canPlace = Boolean(geo.provinciaId && geo.municipioId);
  const [sigpacSourceIndex, setSigpacSourceIndex] = useState(0);
  const sigpacSource = SIGPAC_SOURCES[sigpacSourceIndex] ?? SIGPAC_SOURCES.at(-1)!;

  const handleSigpacTileError = useCallback(() => {
    setSigpacSourceIndex((current) => Math.min(current + 1, SIGPAC_SOURCES.length - 1));
  }, []);

  return (
    <div className="parcel-map-shell config-block animate-reveal-up" style={{ animationDelay: "165ms" }}>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Map className="h-5 w-5 text-data-blue" /> Ubicación del árbol
        </h2>
        <div className="flex items-center gap-3">
          {geo.punto ? (
            <>
              <span className="text-sm font-medium text-sensor-green">
                Punto colocado ({geo.punto.lat.toFixed(6)}, {geo.punto.lng.toFixed(6)})
              </span>
              <Button type="button" size="sm" variant="outline" onClick={() => patchGeo({ punto: null })}>
                <X className="mr-1 h-3 w-3" /> Eliminar punto
              </Button>
            </>
          ) : (
            <span className="text-sm text-muted-foreground">Aún no hay un punto guardado</span>
          )}
        </div>
      </div>

      <div className="relative overflow-hidden rounded-xl border border-border bg-muted/20">
        <MapContainer center={SPAIN_CENTER} zoom={DEFAULT_ZOOM} scrollWheelZoom className="z-0 h-[460px] w-full">
          <MapSizeSynchronizer />
          <TileLayer
            attribution='&copy; <a href="https://www.esri.com/en-us/home">Esri</a>'
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
          <Pane name="sigpac" style={{ zIndex: 500, pointerEvents: "none" }}>
            <WMSTileLayer
              key={`${sigpacSource.url}-${sigpacSource.layers}-${sigpacSource.version}`}
              url={sigpacSource.url}
              layers={sigpacSource.layers}
              format="image/png"
              transparent
              version={sigpacSource.version}
              opacity={0.8}
              attribution="SIGPAC &copy; FEGA / MAPA"
              eventHandlers={{ tileerror: handleSigpacTileError }}
            />
          </Pane>
          <Pane name="labels" style={{ zIndex: 650, pointerEvents: "none" }}>
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
            />
          </Pane>
          <PointPlacementController />
        </MapContainer>
        {!canPlace && <MapDisabledOverlay />}
      </div>

      <div className="mt-4 space-y-2 text-sm">
        <p className="text-muted-foreground">
          Amplía el mapa hasta ver el árbol y haz clic sobre él. El marcador es arrastrable para un ajuste más preciso.
        </p>
        {sigpacSourceIndex > 0 && (
          <p className="text-amber-600">El servicio SIGPAC principal ha fallado y se está usando una fuente alternativa.</p>
        )}
      </div>
    </div>
  );
}
