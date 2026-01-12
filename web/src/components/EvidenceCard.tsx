import { ExternalLink, ThumbsUp, ThumbsDown, Minus } from 'lucide-react';
import type { EvidenceItem } from '../types';

interface Props {
  evidence: EvidenceItem;
}

export function EvidenceCard({ evidence }: Props) {
  const supportIcon =
    evidence.supports_claim === true ? (
      <ThumbsUp className="w-4 h-4 text-emerald-400" />
    ) : evidence.supports_claim === false ? (
      <ThumbsDown className="w-4 h-4 text-red-400" />
    ) : (
      <Minus className="w-4 h-4 text-slate-400" />
    );

  const supportLabel =
    evidence.supports_claim === true
      ? 'Supports'
      : evidence.supports_claim === false
      ? 'Contradicts'
      : 'Neutral';

  return (
    <div className="p-4 rounded-lg bg-slate-800/50 border border-slate-700">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <h4 className="font-medium text-slate-200">{evidence.source_title}</h4>
          {evidence.source_publisher && (
            <p className="text-sm text-slate-500 mt-0.5">
              {evidence.source_publisher}
              {evidence.source_date && ` • ${evidence.source_date}`}
            </p>
          )}
        </div>
        <a
          href={evidence.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="p-2 rounded hover:bg-slate-700 text-slate-400 hover:text-slate-200"
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>

      <p className="mt-3 text-sm text-slate-300">{evidence.summary}</p>

      <div className="mt-3 flex items-center gap-4 text-sm">
        <div className="flex items-center gap-1.5">
          {supportIcon}
          <span className="text-slate-400">{supportLabel}</span>
        </div>
        {evidence.confidence_score && (
          <div className="text-slate-500">
            Confidence: {(parseFloat(evidence.confidence_score) * 100).toFixed(0)}%
          </div>
        )}
      </div>
    </div>
  );
}

