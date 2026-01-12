import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FileText,
  Target,
  Search,
  CheckCircle,
  LogOut,
  RefreshCw,
  Plus,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { editorApi } from '../api/editor';
import { ChainIntegrityBadge } from '../components/ChainIntegrityBadge';
import { ClaimStatusBadge } from '../components/ClaimStatusBadge';
import type { EditorClaimListItem } from '../types';

export function EditorDashboard() {
  const { user, logout, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [claims, setClaims] = useState<EditorClaimListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchClaims = async () => {
    setLoading(true);
    try {
      const data = await editorApi.getClaims();
      setClaims(data);
    } catch {
      // Handle error
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/editor/login');
  };

  useEffect(() => {
    if (!authLoading && !user) {
      navigate('/editor/login');
    }
  }, [user, authLoading, navigate]);

  useEffect(() => {
    if (user) {
      fetchClaims();
    }
  }, [user]);

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <RefreshCw className="w-8 h-8 text-slate-500 animate-spin" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

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
                  Editor Portal
                </h1>
                <p className="text-sm text-slate-500">
                  Logged in as {user.username}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <ChainIntegrityBadge valid={user.ledger_integrity_valid} />
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm font-medium text-slate-300"
              >
                <LogOut className="w-4 h-4" />
                <span>Logout</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700">
            <p className="text-sm text-slate-500">Total Claims</p>
            <p className="text-2xl font-bold text-slate-100 mt-1">
              {user.claim_count}
            </p>
          </div>
          <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700">
            <p className="text-sm text-slate-500">Editor ID</p>
            <p className="text-sm font-mono text-slate-400 mt-1 truncate">
              {user.editor_id.substring(0, 16)}...
            </p>
          </div>
          <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700">
            <p className="text-sm text-slate-500">Role</p>
            <p className="text-lg font-medium text-slate-100 mt-1 capitalize">
              {user.role}
            </p>
          </div>
          <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700">
            <p className="text-sm text-slate-500">Chain Status</p>
            <p className={`text-lg font-medium mt-1 ${user.ledger_integrity_valid ? 'text-emerald-400' : 'text-red-400'}`}>
              {user.ledger_integrity_valid ? '✓ Valid' : '✗ Invalid'}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-slate-200 mb-4">Actions</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Link
              to="/editor/declare"
              className="flex items-center gap-3 p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20 hover:bg-indigo-500/20 transition-colors"
            >
              <Plus className="w-5 h-5 text-indigo-400" />
              <span className="font-medium text-indigo-300">Declare Claim</span>
            </Link>
            <Link
              to="/editor/operationalize"
              className="flex items-center gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 hover:bg-amber-500/20 transition-colors"
            >
              <Target className="w-5 h-5 text-amber-400" />
              <span className="font-medium text-amber-300">Operationalize</span>
            </Link>
            <Link
              to="/editor/evidence"
              className="flex items-center gap-3 p-4 rounded-xl bg-purple-500/10 border border-purple-500/20 hover:bg-purple-500/20 transition-colors"
            >
              <Search className="w-5 h-5 text-purple-400" />
              <span className="font-medium text-purple-300">Add Evidence</span>
            </Link>
            <Link
              to="/editor/resolve"
              className="flex items-center gap-3 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors"
            >
              <CheckCircle className="w-5 h-5 text-emerald-400" />
              <span className="font-medium text-emerald-300">Resolve</span>
            </Link>
          </div>
        </div>

        {/* Claims List */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-200">
              Claims ({claims.length})
            </h2>
            <button
              onClick={fetchClaims}
              disabled={loading}
              className="p-2 rounded-lg hover:bg-slate-800 text-slate-400"
            >
              <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {claims.length === 0 ? (
            <div className="text-center py-12 bg-slate-800/30 rounded-xl border border-slate-700/50">
              <FileText className="w-12 h-12 text-slate-600 mx-auto" />
              <p className="mt-4 text-slate-500">No claims yet</p>
              <Link
                to="/editor/declare"
                className="mt-4 inline-block px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
              >
                Declare your first claim
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {claims.map((claim) => (
                <div
                  key={claim.claim_id}
                  className="flex items-center justify-between p-4 rounded-xl bg-slate-800/50 border border-slate-700/50"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-300 truncate">{claim.statement}</p>
                    <p className="text-xs font-mono text-slate-500 mt-1">
                      {claim.claim_id}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 ml-4">
                    <ClaimStatusBadge status={claim.status} />
                    <Link
                      to={`/claims/${claim.claim_id}`}
                      className="text-sm text-indigo-400 hover:text-indigo-300"
                    >
                      View
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

