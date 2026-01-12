import { useState } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, AlertCircle, CheckCircle } from 'lucide-react';
import { editorApi } from '../api/editor';
import { useAuth } from '../hooks/useAuth';

export function EditorEvidence() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [form, setForm] = useState({
    claim_id: searchParams.get('claim_id') || '',
    source_url: '',
    source_title: '',
    source_publisher: '',
    source_date: '',
    source_type: 'primary',
    evidence_type: 'official_report',
    summary: '',
    supports_claim: 'true',
    relevance_explanation: '',
    confidence_score: '0.8',
    confidence_rationale: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await editorApi.addEvidence(form.claim_id, {
        source_url: form.source_url,
        source_title: form.source_title,
        source_publisher: form.source_publisher || undefined,
        source_date: form.source_date || undefined,
        source_type: form.source_type,
        evidence_type: form.evidence_type,
        summary: form.summary,
        supports_claim: form.supports_claim === 'true',
        relevance_explanation: form.relevance_explanation || undefined,
        confidence_score: form.confidence_score,
        confidence_rationale: form.confidence_rationale || undefined,
      });
      setSuccess(`Evidence added! Event: ${result.event_id.substring(0, 8)}...`);
      setTimeout(() => navigate('/editor'), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add evidence');
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
        <h1 className="text-2xl font-bold text-slate-100 mb-6">Add Evidence</h1>

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

          <fieldset className="p-4 rounded-lg border border-slate-700">
            <legend className="px-2 text-sm font-medium text-slate-400">
              Source Information
            </legend>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Source URL *
                </label>
                <input
                  type="url"
                  value={form.source_url}
                  onChange={(e) => setForm({ ...form, source_url: e.target.value })}
                  required
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="https://..."
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Source Title *
                </label>
                <input
                  type="text"
                  value={form.source_title}
                  onChange={(e) => setForm({ ...form, source_title: e.target.value })}
                  required
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="Title of the report/article"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">
                    Publisher
                  </label>
                  <input
                    type="text"
                    value={form.source_publisher}
                    onChange={(e) => setForm({ ...form, source_publisher: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                    placeholder="e.g., Dept of Finance"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">
                    Source Date
                  </label>
                  <input
                    type="date"
                    value={form.source_date}
                    onChange={(e) => setForm({ ...form, source_date: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">
                    Source Type
                  </label>
                  <select
                    value={form.source_type}
                    onChange={(e) => setForm({ ...form, source_type: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="primary">Primary</option>
                    <option value="secondary">Secondary</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">
                    Evidence Type
                  </label>
                  <select
                    value={form.evidence_type}
                    onChange={(e) => setForm({ ...form, evidence_type: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="official_report">Official Report</option>
                    <option value="statistical_data">Statistical Data</option>
                    <option value="news_article">News Article</option>
                    <option value="research_paper">Research Paper</option>
                  </select>
                </div>
              </div>
            </div>
          </fieldset>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Summary *
            </label>
            <textarea
              value={form.summary}
              onChange={(e) => setForm({ ...form, summary: e.target.value })}
              required
              rows={3}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="What does this evidence show?"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Supports Claim?
              </label>
              <select
                value={form.supports_claim}
                onChange={(e) => setForm({ ...form, supports_claim: e.target.value })}
                className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              >
                <option value="true">Yes - supports</option>
                <option value="false">No - contradicts</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Confidence Score (0-1)
              </label>
              <input
                type="text"
                value={form.confidence_score}
                onChange={(e) => setForm({ ...form, confidence_score: e.target.value })}
                className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder="0.8"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Adding...' : 'Add Evidence'}
          </button>
        </form>
      </main>
    </div>
  );
}

