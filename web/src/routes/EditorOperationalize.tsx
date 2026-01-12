import { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, AlertCircle, CheckCircle } from 'lucide-react';
import { editorApi } from '../api/editor';
import { useAuth } from '../hooks/useAuth';

export function EditorOperationalize() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [form, setForm] = useState({
    claim_id: searchParams.get('claim_id') || '',
    outcome_description: '',
    metrics: '',
    direction_of_change: 'decrease',
    baseline_value: '',
    baseline_date: '',
    start_date: '',
    evaluation_date: '',
    tolerance_window_days: '30',
    success_conditions: '',
    partial_success_conditions: '',
    failure_conditions: '',
    notes: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await editorApi.operationalizeClaim(form.claim_id, {
        outcome_description: form.outcome_description,
        metrics: form.metrics.split(',').map((m) => m.trim()).filter(Boolean),
        direction_of_change: form.direction_of_change,
        baseline_value: form.baseline_value || undefined,
        baseline_date: form.baseline_date || undefined,
        start_date: form.start_date,
        evaluation_date: form.evaluation_date,
        tolerance_window_days: parseInt(form.tolerance_window_days) || 30,
        success_conditions: form.success_conditions.split('\n').map((s) => s.trim()).filter(Boolean),
        partial_success_conditions: form.partial_success_conditions
          ? form.partial_success_conditions.split('\n').map((s) => s.trim()).filter(Boolean)
          : undefined,
        failure_conditions: form.failure_conditions
          ? form.failure_conditions.split('\n').map((s) => s.trim()).filter(Boolean)
          : undefined,
        notes: form.notes || undefined,
      });
      setSuccess(`Claim operationalized! Event: ${result.event_id.substring(0, 8)}...`);
      setTimeout(() => navigate('/editor'), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to operationalize');
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
        <h1 className="text-2xl font-bold text-slate-100 mb-6">Operationalize Claim</h1>

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
              Expected Outcome
            </legend>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Description *
                </label>
                <textarea
                  value={form.outcome_description}
                  onChange={(e) => setForm({ ...form, outcome_description: e.target.value })}
                  required
                  rows={2}
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="What should happen if the claim is true?"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Metrics * (comma-separated)
                </label>
                <input
                  type="text"
                  value={form.metrics}
                  onChange={(e) => setForm({ ...form, metrics: e.target.value })}
                  required
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="metric1, metric2"
                />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">
                    Direction
                  </label>
                  <select
                    value={form.direction_of_change}
                    onChange={(e) => setForm({ ...form, direction_of_change: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="decrease">Decrease</option>
                    <option value="increase">Increase</option>
                    <option value="no_change">No Change</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">
                    Baseline Value
                  </label>
                  <input
                    type="text"
                    value={form.baseline_value}
                    onChange={(e) => setForm({ ...form, baseline_value: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                    placeholder="$2,500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">
                    Baseline Date
                  </label>
                  <input
                    type="date"
                    value={form.baseline_date}
                    onChange={(e) => setForm({ ...form, baseline_date: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>
            </div>
          </fieldset>

          <fieldset className="p-4 rounded-lg border border-slate-700">
            <legend className="px-2 text-sm font-medium text-slate-400">
              Timeframe
            </legend>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Start Date *
                </label>
                <input
                  type="date"
                  value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                  required
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Evaluation Date *
                </label>
                <input
                  type="date"
                  value={form.evaluation_date}
                  onChange={(e) => setForm({ ...form, evaluation_date: e.target.value })}
                  required
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  Tolerance (days)
                </label>
                <input
                  type="number"
                  value={form.tolerance_window_days}
                  onChange={(e) => setForm({ ...form, tolerance_window_days: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>
          </fieldset>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Success Conditions * (one per line)
            </label>
            <textarea
              value={form.success_conditions}
              onChange={(e) => setForm({ ...form, success_conditions: e.target.value })}
              required
              rows={3}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="Median rent <= $2,125/month"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Notes
            </label>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              rows={2}
              className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="Additional context..."
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Processing...' : 'Operationalize'}
          </button>
        </form>
      </main>
    </div>
  );
}

