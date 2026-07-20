import clsx from "clsx";

interface StatCardProps {
  label: string;
  value: string;
  delta?: string;
  deltaPositive?: boolean;
}

export function StatCard({ label, value, delta, deltaPositive }: StatCardProps) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-semibold text-gray-100">{value}</div>
      {delta && (
        <div className={clsx("text-xs mt-1", deltaPositive ? "text-bullish" : "text-bearish")}>
          {delta}
        </div>
      )}
    </div>
  );
}
