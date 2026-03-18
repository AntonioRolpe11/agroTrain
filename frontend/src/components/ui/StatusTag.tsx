export type StatusTone = "neutral" | "success" | "warning" | "danger";

export function StatusTag({ tone, children }: { tone: StatusTone; children: string }) {
  const cls =
    tone === "success" ? "border-sensor-green/25 bg-sensor-green/10 text-sensor-green"
    : tone === "warning" ? "border-satellite-amber/25 bg-satellite-amber/10 text-satellite-amber"
    : tone === "danger" ? "border-destructive/25 bg-destructive/10 text-destructive"
    : "border-border bg-muted/40 text-muted-foreground";
  return <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${cls}`}>{children}</span>;
}
