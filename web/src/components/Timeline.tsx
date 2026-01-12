import { FileText, Target, Search, CheckCircle } from 'lucide-react';
import type { TimelineEvent } from '../types';

interface Props {
  events: TimelineEvent[];
}

const eventIcons: Record<string, typeof FileText> = {
  CLAIM_DECLARED: FileText,
  CLAIM_OPERATIONALIZED: Target,
  EVIDENCE_ADDED: Search,
  CLAIM_RESOLVED: CheckCircle,
};

const eventColors: Record<string, string> = {
  CLAIM_DECLARED: 'bg-blue-500',
  CLAIM_OPERATIONALIZED: 'bg-amber-500',
  EVIDENCE_ADDED: 'bg-purple-500',
  CLAIM_RESOLVED: 'bg-emerald-500',
};

export function Timeline({ events }: Props) {
  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-slate-700" />

      <div className="space-y-4">
        {events.map((event, index) => {
          const Icon = eventIcons[event.event_type] || FileText;
          const color = eventColors[event.event_type] || 'bg-slate-500';

          return (
            <div key={event.event_id} className="relative flex gap-4">
              {/* Icon */}
              <div
                className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full ${color}`}
              >
                <Icon className="w-4 h-4 text-white" />
              </div>

              {/* Content */}
              <div className="flex-1 pb-4">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-200">
                    {event.event_type.replace(/_/g, ' ')}
                  </span>
                  <span className="text-xs text-slate-500">#{event.seq}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {new Date(event.created_at).toLocaleString()}
                </div>
                <div className="mt-2 font-mono text-xs text-slate-600 break-all">
                  {event.event_hash.substring(0, 32)}...
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

