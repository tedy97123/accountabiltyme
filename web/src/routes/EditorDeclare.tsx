import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, AlertCircle, CheckCircle } from 'lucide-react';
import { editorApi } from '../api/editor';
import { useAuth } from '../hooks/useAuth';

export function EditorDeclare() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [form, setForm] = useState({
    statement: '',
    statement_context: '',
    source_url: '',
    claim_type: 'predictive',
    geographic: '',
    policy_domain: '',
    affected_population: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await editorApi.declareClaim(form);
      setSuccess(`Claim declared! Event: ${result.event_id.substring(0, 8)}...`);
      setTimeout(() => navigate('/editor'), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to declare claim');
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
        <h1 className="text-2xl font-bold text-slate-100 mb-6">Declare Claim</h1>

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
              Statement *
            </label>
            <textarea
              value={form.statement}
              onChange={(e) => setForm({ ...form, statement: e.target.value })}
              required
              minLength={10}
              rows={3}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="The specific claim being made..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Context
            </label>
            <input
              type="text"
              value={form.statement_context}
              onChange={(e) => setForm({ ...form, statement_context: e.target.value })}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="Where/when was this claim made?"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Source URL
            </label>
            <input
              type="url"
              value={form.source_url}
              onChange={(e) => setForm({ ...form, source_url: e.target.value })}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="https://..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Claim Type
            </label>
            <select
              value={form.claim_type}
              onChange={(e) => setForm({ ...form, claim_type: e.target.value })}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            >
              <option value="predictive">Predictive</option>
              <option value="descriptive">Descriptive</option>
              <option value="causal">Causal</option>
            </select>
          </div>

          <fieldset className="p-4 rounded-lg border border-slate-700">
            <legend className="px-2 text-sm font-medium text-slate-400">
              Scope (optional)
            </legend>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Geographic
                </label>
                <input
                  type="text"
                  value={form.geographic}
                  onChange={(e) => setForm({ ...form, geographic: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g., California, USA"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Policy Domain
                </label>
                <input
                  type="text"
                  value={form.policy_domain}
                  onChange={(e) => setForm({ ...form, policy_domain: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g., housing, healthcare"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Affected Population
                </label>
                <input
                  type="text"
                  value={form.affected_population}
                  onChange={(e) => setForm({ ...form, affected_population: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g., renters, seniors"
                />
              </div>
            </div>
          </fieldset>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Creating...' : 'Create Claim'}
          </button>
        </form>
      </main>
    </div>
  );
}

