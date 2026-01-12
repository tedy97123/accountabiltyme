import { CheckCircle, XCircle } from 'lucide-react';

interface Props {
  valid: boolean;
  showLabel?: boolean;
}

export function ChainIntegrityBadge({ valid, showLabel = true }: Props) {
  if (valid) {
    return (
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-sm font-medium">
        <CheckCircle className="w-4 h-4" />
        {showLabel && <span>Chain Valid</span>}
      </div>
    );
  }

  return (
    <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-500/10 text-red-400 text-sm font-medium">
      <XCircle className="w-4 h-4" />
      {showLabel && <span>Chain Invalid</span>}
    </div>
  );
}

