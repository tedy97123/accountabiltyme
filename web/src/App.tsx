import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth';

// Public routes
import { PublicClaims } from './routes/PublicClaims';
import { PublicClaimDetail } from './routes/PublicClaimDetail';
import { Verify } from './routes/Verify';

// Editor routes
import { EditorLogin } from './routes/EditorLogin';
import { EditorDashboard } from './routes/EditorDashboard';
import { EditorDeclare } from './routes/EditorDeclare';
import { EditorOperationalize } from './routes/EditorOperationalize';
import { EditorEvidence } from './routes/EditorEvidence';
import { EditorResolve } from './routes/EditorResolve';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<Navigate to="/claims" replace />} />
          <Route path="/claims" element={<PublicClaims />} />
          <Route path="/claims/:claimId" element={<PublicClaimDetail />} />
          <Route path="/verify" element={<Verify />} />

          {/* Editor routes */}
          <Route path="/editor/login" element={<EditorLogin />} />
          <Route path="/editor" element={<EditorDashboard />} />
          <Route path="/editor/declare" element={<EditorDeclare />} />
          <Route path="/editor/operationalize" element={<EditorOperationalize />} />
          <Route path="/editor/evidence" element={<EditorEvidence />} />
          <Route path="/editor/resolve" element={<EditorResolve />} />

          {/* 404 */}
          <Route
            path="*"
            element={
              <div className="min-h-screen flex items-center justify-center">
                <div className="text-center">
                  <h1 className="text-4xl font-bold text-slate-100 mb-4">404</h1>
                  <p className="text-slate-500 mb-6">Page not found</p>
                  <a
                    href="/claims"
                    className="text-indigo-400 hover:text-indigo-300"
                  >
                    Go to claims →
                  </a>
                </div>
              </div>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
