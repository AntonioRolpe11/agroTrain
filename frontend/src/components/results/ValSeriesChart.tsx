import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { ValSeries } from "@/types/api";

interface Props {
  target: string;
  series: ValSeries;
}

export function ValSeriesChart({ target, series }: Props) {
  const data = series.y_true.map((val, i) => ({
    idx: i + 1,
    Real: parseFloat(val.toFixed(4)),
    Predicho: parseFloat(series.y_pred[i].toFixed(4)),
  }));

  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">{target} — validación</p>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis
            dataKey="idx"
            tick={{ fontSize: 10 }}
            label={{ value: "muestra", position: "insideBottomRight", offset: -4, fontSize: 10 }}
          />
          <YAxis tick={{ fontSize: 10 }} width={48} />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 6 }}
            formatter={(v: number) => v.toFixed(4)}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="Real"
            stroke="#5b8c3a"
            dot={false}
            strokeWidth={1.5}
          />
          <Line
            type="monotone"
            dataKey="Predicho"
            stroke="#e08c2a"
            dot={false}
            strokeWidth={1.5}
            strokeDasharray="4 2"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
