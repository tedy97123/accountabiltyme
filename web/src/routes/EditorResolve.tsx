import { useState } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, AlertCircle, CheckCircle } from 'lucide-react';
import { editorApi } from '../api/editor';
import { useAuth } from '../hooks/useAuth';

export function EditorResolve() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [form, setForm] = useState({
    claim_id: searchParams.get('claim_id') || '',
    resolution: 'met',
    resolution_summary: '',
    supporting_evidence_ids: '',
    resolution_details: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await editorApi.resolveClaim(form.claim_id, {
        resolution: form.resolution,
        resolution_summary: form.resolution_summary,
        supporting_evidence_ids: form.supporting_evidence_ids
          .split(',')
          .map((id) => id.trim())
          .filter(Boolean),
        resolution_details: form.resolution_details || undefined,
      });
      setSuccess(`Claim resolved! Event: ${result.event_id.substring(0, 8)}...`);
      setTimeout(() => navigate('/editor'), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resolve claim');
    } finally {
      setLoading(false);
    }
  };

  if (!user) {
    navigate('/editor/login');
    return null;
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <Link
            to="/editor"
            className="inline-flex items-center gap-2 text-slate-400 hover:text-slate-200"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to dashboard</span>
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-slate-100 mb-6">Resolve Claim</h1>

        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {success && (
          <div className="mb-6 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-3">
            <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <p className="text-sm text-emerald-400">{success}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Claim ID *
            </label>
            <input
              type="text"
              value={form.claim_id}
              onChange={(e) => setForm({ ...form, claim_id: e.target.value })}
              required
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono text-sm"
              placeholder="UUID from dashboard"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Resolution *
            </label>
            <select
              value={form.resolution}
              onChange={(e) => setForm({ ...form, resolution: e.target.value })}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            >
              <option value="met">Met - claim was accurate</option>
              <option value="partially_met">Partially Met - partially accurate</option>
              <option value="not_met">Not Met - claim was inaccurate</option>
              <option value="inconclusive">Inconclusive - cannot determine</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Resolution Summary * (min 20 characters)
            </label>
            <textarea
              value={form.resolution_summary}
              onChange={(e) => setForm({ ...form, resolution_summary: e.target.value })}
              required
              minLength={20}
              rows={4}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="Detailed explanation of the resolution decision..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Supporting Evidence IDs (comma-separated UUIDs)
            </label>
            <input
              type="text"
              value={form.supporting_evidence_ids}
              onChange={(e) => setForm({ ...form, supporting_evidence_ids: e.target.value })}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono text-sm"
              placeholder="uuid1, uuid2, ..."
            />
            <p className="mt-1 text-xs text-slate-500">
              Required for met/partially_met/not_met resolutions
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Resolution Details
            </label>
            <textarea
              value={form.resolution_details}
              onChange={(e) => setForm({ ...form, resolution_details: e.target.value })}
              rows={3}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="Additional analysis, numbers, context..."
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Resolving...' : 'Resolve Claim'}
          </button>
        </form>
      </main>
    </div>
  );
}

