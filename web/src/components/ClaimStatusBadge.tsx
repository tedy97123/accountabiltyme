interface Props {
  status: string;
}

const statusColors: Record<string, string> = {
  declared: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  operationalized: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  observing: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  resolved: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  unknown: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

const statusLabels: Record<string, string> = {
  declared: 'Declared',
  operationalized: 'Operationalized',
  observing: 'Observing',
  resolved: 'Resolved',
  unknown: 'Unknown',
};

export function ClaimStatusBadge({ status }: Props) {
  const normalizedStatus = status.toLowerCase();
  const colorClass = statusColors[normalizedStatus] || statusColors.unknown;
  const label = statusLabels[normalizedStatus] || status;

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${colorClass}`}
    >
      {label}
    </span>
  );
}

