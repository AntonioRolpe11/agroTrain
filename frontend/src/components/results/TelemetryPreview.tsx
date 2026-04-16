import type { TelemetryExtractResponse } from "@/types/api";

export function TelemetryPreview({ extractedTelemetry }: { extractedTelemetry: TelemetryExtractResponse }) {
  return (
    <div className="mt-4">
      <p className="mb-2 text-sm font-medium">
        Vista previa · {extractedTelemetry.points.length} fechas · Índices: {extractedTelemetry.indices.join(", ")}
      </p>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-xs">
          <thead className="bg-muted/40">
            <tr>
              <th className="px-3 py-2 font-medium">Fecha</th>
              {extractedTelemetry.indices.map((idx) => <th key={idx} className="px-3 py-2 font-medium">{idx}</th>)}
              <th className="px-3 py-2 font-medium">Nubosidad %</th>
            </tr>
          </thead>
          <tbody>
            {extractedTelemetry.points.slice(0, 5).map((point, i) => (
              <tr key={i} className="border-t border-border">
                <td className="px-3 py-2">{point.date}</td>
                {extractedTelemetry.indices.map((idx) => <td key={idx} className="px-3 py-2">{point.values[idx] ?? "-"}</td>)}
                <td className="px-3 py-2">{point.cloudCover ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
