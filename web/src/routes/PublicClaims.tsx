import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, RefreshCw } from 'lucide-react';
import { publicApi } from '../api/public';
import { ChainIntegrityBadge } from '../components/ChainIntegrityBadge';
import { ClaimStatusBadge } from '../components/ClaimStatusBadge';
import type { ClaimListItem, IntegrityStatus } from '../types';

export function PublicClaims() {
  const [claims, setClaims] = useState<ClaimListItem[]>([]);
  const [integrity, setIntegrity] = useState<IntegrityStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [claimsData, integrityData] = await Promise.all([
        publicApi.getClaims(),
        publicApi.getIntegrity(),
      ]);
      setClaims(claimsData);
      setIntegrity(integrityData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load claims');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-indigo-500/10">
                <FileText className="w-6 h-6 text-indigo-400" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-100">
                  AccountabilityMe
                </h1>
                <p className="text-sm text-slate-500">Claim Accountability Ledger</p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              {integrity && (
                <ChainIntegrityBadge valid={integrity.ledger_integrity_valid} />
              )}
              <button
                onClick={fetchData}
                disabled={loading}
                className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 disabled:opacity-50"
              >
                <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <Link
                to="/editor"
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm font-medium text-slate-300"
              >
                Editor Portal
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400">
            {error}
          </div>
        )}

        {loading && claims.length === 0 ? (
          <div className="text-center py-12">
            <RefreshCw className="w-8 h-8 text-slate-500 animate-spin mx-auto" />
            <p className="mt-4 text-slate-500">Loading claims...</p>
          </div>
        ) : claims.length === 0 ? (
          <div className="text-center py-12">
            <FileText className="w-12 h-12 text-slate-600 mx-auto" />
            <h2 className="mt-4 text-lg font-medium text-slate-400">No claims yet</h2>
            <p className="mt-2 text-slate-500">
              Claims will appear here once they are declared.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium text-slate-200">
                All Claims ({claims.length})
              </h2>
              {integrity && (
                <span className="text-sm text-slate-500">
                  {integrity.event_count} events in chain
                </span>
              )}
            </div>

            <div className="grid gap-4">
              {claims.map((claim) => (
                <Link
                  key={claim.claim_id}
                  to={`/claims/${claim.claim_id}`}
                  className="block p-5 rounded-xl bg-slate-800/50 border border-slate-700/50 hover:border-slate-600 hover:bg-slate-800 transition-all"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-slate-200 font-medium line-clamp-2">
                        {claim.statement}
                      </p>
                      <div className="mt-2 flex items-center gap-3 text-sm text-slate-500">
                        <span className="font-mono text-xs">
                          {claim.claim_id.substring(0, 8)}...
                        </span>
                        {claim.declared_at && (
                          <span>
                            {new Date(claim.declared_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                    <ClaimStatusBadge status={claim.status} />
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

