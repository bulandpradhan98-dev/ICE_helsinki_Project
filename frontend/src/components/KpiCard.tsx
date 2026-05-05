type KpiCardProps = {
  label: string;
  value: string;
  tone?: "default" | "success" | "warning";
};

export function KpiCard({ label, value, tone = "default" }: KpiCardProps) {
  return (
    <article className={`kpi-card tone-${tone}`}>
      <span className="kpi-label">{label}</span>
      <strong className="kpi-value">{value}</strong>
    </article>
  );
}

