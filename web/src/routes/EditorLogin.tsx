import { useState, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Lock, ArrowLeft, AlertCircle } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

export function EditorLogin() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    // Use refs to get values (works better with browser automation)
    const username = usernameRef.current?.value || '';
    const password = passwordRef.current?.value || '';

    try {
      await login({ username, password });
      navigate('/editor');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <Link
          to="/claims"
          className="inline-flex items-center gap-2 text-slate-400 hover:text-slate-200 mb-8"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to public claims</span>
        </Link>

        <div className="p-8 rounded-2xl bg-slate-800/50 border border-slate-700">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2.5 rounded-lg bg-indigo-500/10">
              <Lock className="w-6 h-6 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-100">Editor Login</h1>
              <p className="text-sm text-slate-500">Access the editor portal</p>
            </div>
          </div>

          {error && (
            <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="username"
                className="block text-sm font-medium text-slate-300 mb-2"
              >
                Username
              </label>
              <input
                id="username"
                type="text"
                ref={usernameRef}
                required
                autoFocus
                className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder="Enter username"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-slate-300 mb-2"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                ref={passwordRef}
                required
                className="w-full px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder="Enter password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

