import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Download, RefreshCw, ExternalLink, ShieldCheck, FileJson } from 'lucide-react';
import { publicApi } from '../api/public';
import { ChainIntegrityBadge } from '../components/ChainIntegrityBadge';
import { ClaimStatusBadge } from '../components/ClaimStatusBadge';
import { Timeline } from '../components/Timeline';
import { EvidenceCard } from '../components/EvidenceCard';
import type { ClaimDetail } from '../types';

export function PublicClaimDetail() {
  const { claimId } = useParams<{ claimId: string }>();
  const [claim, setClaim] = useState<ClaimDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    if (!claimId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await publicApi.getClaim(claimId);
      setClaim(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load claim');
    } finally {
      setLoading(false);
    }
  };

  const handleExportMarkdown = async () => {
    if (!claimId) return;
    try {
      const data = await publicApi.exportMarkdown(claimId);
      const blob = new Blob([data.markdown], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `claim-${claimId.substring(0, 8)}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Markdown export failed:', err);
    }
  };

  const handleDownloadBundle = async () => {
    if (!claimId) return;
    try {
      const response = await fetch(`/api/public/claims/${claimId}/bundle.json`);
      if (!response.ok) throw new Error('Failed to download bundle');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `claim-${claimId.substring(0, 8)}-bundle.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Bundle download failed:', err);
    }
  };

  useEffect(() => {
    fetchData();
  }, [claimId]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <RefreshCw className="w-8 h-8 text-slate-500 animate-spin" />
      </div>
    );
  }

  if (error || !claim) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error || 'Claim not found'}</p>
          <Link
            to="/claims"
            className="text-indigo-400 hover:text-indigo-300"
          >
            ← Back to claims
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link
              to="/claims"
              className="flex items-center gap-2 text-slate-400 hover:text-slate-200"
            >
              <ArrowLeft className="w-5 h-5" />
              <span>Back to claims</span>
            </Link>

            <div className="flex items-center gap-3">
              <ChainIntegrityBadge valid={claim.ledger_integrity_valid} />
              <button
                onClick={handleDownloadBundle}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-sm text-white font-medium"
                title="Download verifiable bundle (JSON) - independently verify this claim"
              >
                <ShieldCheck className="w-4 h-4" />
                <span>Verify Bundle</span>
              </button>
              <button
                onClick={handleExportMarkdown}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm text-slate-300"
                title="Export as Markdown report"
              >
                <Download className="w-4 h-4" />
                <span>Export MD</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="grid lg:grid-cols-3 gap-8">
          {/* Main Column */}
          <div className="lg:col-span-2 space-y-8">
            {/* Statement */}
            <section>
              <div className="flex items-center gap-3 mb-4">
                <ClaimStatusBadge status={claim.status} />
                <span className="font-mono text-xs text-slate-500">
                  {claim.claim_id}
                </span>
              </div>
              <h1 className="text-2xl font-bold text-slate-100">
                {claim.declared?.statement as string || 'Untitled Claim'}
              </h1>
              {claim.declared?.statement_context && (
                <p className="mt-3 text-slate-400">
                  {claim.declared.statement_context as string}
                </p>
              )}
              {claim.declared?.source_url && (
                <a
                  href={claim.declared.source_url as string}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex items-center gap-1.5 text-sm text-indigo-400 hover:text-indigo-300"
                >
                  <ExternalLink className="w-4 h-4" />
                  <span>Source</span>
                </a>
              )}
            </section>

            {/* Operationalization */}
            {claim.operationalized && (
              <section className="p-5 rounded-xl bg-slate-800/50 border border-slate-700">
                <h2 className="text-lg font-semibold text-slate-200 mb-4">
                  Operationalization
                </h2>
                <div className="space-y-4 text-sm">
                  {claim.operationalized.expected_outcome && (
                    <div>
                      <h3 className="font-medium text-slate-400 mb-1">
                        Expected Outcome
                      </h3>
                      <p className="text-slate-300">
                        {(claim.operationalized.expected_outcome as any)?.description}
                      </p>
                    </div>
                  )}
                  {claim.operationalized.timeframe && (
                    <div>
                      <h3 className="font-medium text-slate-400 mb-1">
                        Timeframe
                      </h3>
                      <p className="text-slate-300">
                        {(claim.operationalized.timeframe as any)?.start_date} →{' '}
                        {(claim.operationalized.timeframe as any)?.evaluation_date}
                      </p>
                    </div>
                  )}
                  {claim.operationalized.evaluation_criteria && (
                    <div>
                      <h3 className="font-medium text-slate-400 mb-1">
                        Success Conditions
                      </h3>
                      <ul className="list-disc list-inside text-slate-300 space-y-1">
                        {((claim.operationalized.evaluation_criteria as any)?.success_conditions || []).map(
                          (condition: string, i: number) => (
                            <li key={i}>{condition}</li>
                          )
                        )}
                      </ul>
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* Evidence */}
            <section>
              <h2 className="text-lg font-semibold text-slate-200 mb-4">
                Evidence ({claim.evidence.length})
              </h2>
              {claim.evidence.length === 0 ? (
                <p className="text-slate-500">No evidence yet.</p>
              ) : (
                <div className="space-y-4">
                  {claim.evidence.map((ev) => (
                    <EvidenceCard key={ev.evidence_id} evidence={ev} />
                  ))}
                </div>
              )}
            </section>

            {/* Resolution */}
            {claim.resolved && (
              <section className="p-5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                <h2 className="text-lg font-semibold text-emerald-400 mb-4">
                  Resolution: {(claim.resolved.resolution as string)?.toUpperCase()}
                </h2>
                <p className="text-slate-300">
                  {claim.resolved.resolution_summary as string}
                </p>
                {claim.resolved.resolution_details && (
                  <p className="mt-3 text-sm text-slate-400">
                    {claim.resolved.resolution_details as string}
                  </p>
                )}
              </section>
            )}
          </div>

          {/* Sidebar - Timeline */}
          <div className="lg:col-span-1">
            <div className="sticky top-24 space-y-6">
              <div>
                <h2 className="text-lg font-semibold text-slate-200 mb-4">
                  Event Timeline
                </h2>
                <Timeline events={claim.timeline} />
              </div>

              {/* Verification Info */}
              <div className="p-4 rounded-xl bg-slate-800/30 border border-slate-700/50">
                <div className="flex items-center gap-2 mb-3">
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  <h3 className="font-medium text-slate-200">Verify Independently</h3>
                </div>
                <p className="text-sm text-slate-400 mb-3">
                  Download the verification bundle to independently verify this claim 
                  without trusting our servers.
                </p>
                <button
                  onClick={handleDownloadBundle}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/30 text-sm text-emerald-400 font-medium"
                >
                  <FileJson className="w-4 h-4" />
                  <span>Download Bundle</span>
                </button>
                <p className="mt-2 text-xs text-slate-500">
                  Contains events, signatures, and hashes for verification.
                </p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

