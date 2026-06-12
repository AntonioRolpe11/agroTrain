import { useEffect } from "react";
import L from "leaflet";
import { MapPin } from "lucide-react";
import { MapContainer, Pane, TileLayer, useMap } from "react-leaflet";

const sensorIcon = L.divIcon({
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

interface SensorLocationMapProps {
  punto: { lat: number; lng: number };
}

function StaticMarker({ punto }: SensorLocationMapProps) {
  const map = useMap();
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => { map.invalidateSize(); });
    const latlng = L.latLng(punto.lat, punto.lng);
    const marker = L.marker(latlng, { icon: sensorIcon, interactive: false });
    marker.addTo(map);
    map.setView(latlng, 17);
    return () => {
      window.cancelAnimationFrame(frame);
      map.removeLayer(marker);
    };
  }, [map, punto.lat, punto.lng]);
  return null;
}

export function SensorLocationMap({ punto }: SensorLocationMapProps) {
  return (
    <div className="config-block">
      <div className="mb-4 flex items-start gap-3">
        <div className="rounded-lg bg-primary/10 p-2 text-olive"><MapPin className="h-5 w-5" /></div>
        <div>
          <h2 className="text-lg font-semibold">Ubicación del sensor digital</h2>
          <p className="text-sm text-muted-foreground">
            Punto donde está colocado el sensor ({punto.lat.toFixed(6)}, {punto.lng.toFixed(6)}).
          </p>
        </div>
      </div>
      <div className="relative overflow-hidden rounded-xl border border-border bg-muted/20">
        <MapContainer center={[punto.lat, punto.lng]} zoom={17} scrollWheelZoom className="z-0 h-[360px] w-full">
          <TileLayer
            attribution='&copy; <a href="https://www.esri.com/en-us/home">Esri</a>'
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
          <Pane name="labels" style={{ zIndex: 650, pointerEvents: "none" }}>
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
            />
          </Pane>
          <StaticMarker punto={punto} />
        </MapContainer>
      </div>
    </div>
  );
}
