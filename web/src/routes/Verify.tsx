import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Shield,
  Upload,
  CheckCircle,
  XCircle,
  AlertTriangle,
  FileJson,
  ArrowLeft,
  Hash,
  Key,
  Link as LinkIcon,
  Users,
} from 'lucide-react';

// ============================================================
// Types
// ============================================================

interface VerificationResult {
  result: 'VERIFIED' | 'TAMPERED' | 'INCOMPLETE' | 'INVALID_FORMAT';
  claimId: string;
  eventCount: number;
  checksPassed: string[];
  checksFailed: string[];
  warnings: string[];
  details: {
    bundleVersion?: string;
    specVersion?: string;
    exportedAt?: string;
    chainValidAtExport?: boolean;
  };
}

interface BundleEvent {
  event_id: string;
  sequence_number: number;
  event_type: string;
  payload: Record<string, unknown>;
  previous_event_hash: string | null;
  event_hash: string;
  created_by: string;
  editor_signature: string;
}

interface Bundle {
  _meta: {
    bundle_version: string;
    spec_version: string;
    exported_at: string;
    claim_id: string;
    chain_valid_at_export: boolean;
  };
  _verification: {
    canonicalization_version: number;
    hash_algorithm: string;
    signature_algorithm: string;
  };
  claim: {
    claim_id: string;
    status: string;
    event_count: number;
  };
  events: BundleEvent[];
  editors: Record<string, { public_key: string; username: string }>;
}

// ============================================================
// Verification Logic (matches spec/v1.md)
// ============================================================

const SERIALIZATION_VERSION = 1;

async function sha256(message: string): Promise<string> {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

function canonicalize(data: Record<string, unknown>): string {
  const canonical = toCanonicalDict(data);
  const withVersion = { __canon_v: SERIALIZATION_VERSION, ...canonical };
  return JSON.stringify(withVersion, Object.keys(withVersion).sort());
}

function toCanonicalDict(data: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  const sortedKeys = Object.keys(data).sort();

  for (const key of sortedKeys) {
    const value = data[key];
    if (value === null || value === undefined) continue;

    if (typeof value === 'object' && !Array.isArray(value)) {
      result[key] = toCanonicalDict(value as Record<string, unknown>);
    } else if (Array.isArray(value)) {
      result[key] = value.map((v) =>
        typeof v === 'object' && v !== null && !Array.isArray(v)
          ? toCanonicalDict(v as Record<string, unknown>)
          : v
      );
    } else {
      result[key] = value;
    }
  }

  return result;
}

async function computeEventHash(
  payload: Record<string, unknown>,
  previousHash: string | null
): Promise<string> {
  const canonical = canonicalize(payload);

  if (!previousHash) {
    return sha256(canonical);
  }

  return sha256(`${previousHash.toLowerCase()}:${canonical}`);
}

async function verifySignature(
  eventHash: string,
  signatureB64: string,
  publicKeyB64: string
): Promise<boolean> {
  try {
    // Import the Ed25519 public key
    const publicKeyBytes = Uint8Array.from(atob(publicKeyB64), (c) =>
      c.charCodeAt(0)
    );

    const publicKey = await crypto.subtle.importKey(
      'raw',
      publicKeyBytes,
      { name: 'Ed25519' },
      false,
      ['verify']
    );

    // Decode signature
    const signatureBytes = Uint8Array.from(atob(signatureB64), (c) =>
      c.charCodeAt(0)
    );

    // Hash bytes (the signature is over the hash bytes, not the hex string)
    const hashBytes = new Uint8Array(
      eventHash.match(/.{2}/g)!.map((byte) => parseInt(byte, 16))
    );

    // Verify
    return await crypto.subtle.verify('Ed25519', publicKey, signatureBytes, hashBytes);
  } catch {
    // Ed25519 might not be supported in all browsers
    // Return null to indicate "cannot verify" rather than "invalid"
    return false;
  }
}

async function verifyBundle(bundle: Bundle): Promise<VerificationResult> {
  const checksPassed: string[] = [];
  const checksFailed: string[] = [];
  const warnings: string[] = [];

  // 1. Check structure
  if (!bundle._meta || !bundle.events || !bundle.editors) {
    return {
      result: 'INVALID_FORMAT',
      claimId: 'unknown',
      eventCount: 0,
      checksPassed: [],
      checksFailed: ['Bundle missing required fields (_meta, events, editors)'],
      warnings: [],
      details: {},
    };
  }

  checksPassed.push('Bundle structure valid');

  // 2. Verify hashes
  let hashesValid = true;
  for (let i = 0; i < bundle.events.length; i++) {
    const event = bundle.events[i];
    const prevHash = event.previous_event_hash;

    try {
      const computed = await computeEventHash(event.payload, prevHash);
      if (computed.toLowerCase() !== event.event_hash.toLowerCase()) {
        checksFailed.push(
          `Event ${event.event_id.substring(0, 8)}: Hash mismatch`
        );
        hashesValid = false;
      }
    } catch (e) {
      checksFailed.push(
        `Event ${event.event_id.substring(0, 8)}: Failed to compute hash`
      );
      hashesValid = false;
    }
  }

  if (hashesValid) {
    checksPassed.push(`All ${bundle.events.length} event hashes verified`);
  }

  // 3. Verify chain linkage
  let chainValid = true;
  for (let i = 1; i < bundle.events.length; i++) {
    const prevEvent = bundle.events[i - 1];
    const currEvent = bundle.events[i];

    if (
      prevEvent.event_hash.toLowerCase() !==
      currEvent.previous_event_hash?.toLowerCase()
    ) {
      checksFailed.push(`Chain break at event ${i}`);
      chainValid = false;
    }
  }

  if (chainValid) {
    checksPassed.push('Chain linkage verified');
  }

  // 4. Verify signatures (if Ed25519 is supported)
  let signaturesValid = true;
  let signaturesChecked = 0;

  for (const event of bundle.events) {
    const editor = bundle.editors[event.created_by];
    if (!editor?.public_key) {
      checksFailed.push(
        `Event ${event.event_id.substring(0, 8)}: Missing editor public key`
      );
      signaturesValid = false;
      continue;
    }

    try {
      const valid = await verifySignature(
        event.event_hash,
        event.editor_signature,
        editor.public_key
      );

      if (!valid) {
        checksFailed.push(
          `Event ${event.event_id.substring(0, 8)}: Signature invalid`
        );
        signaturesValid = false;
      } else {
        signaturesChecked++;
      }
    } catch {
      warnings.push('Ed25519 signature verification not supported in this browser');
      break;
    }
  }

  if (signaturesValid && signaturesChecked > 0) {
    checksPassed.push(`All ${signaturesChecked} signatures verified`);
  } else if (signaturesChecked === 0 && warnings.length > 0) {
    // Browser doesn't support Ed25519
  }

  // 5. Check editors present
  const editorIds = new Set(bundle.events.map((e) => e.created_by));
  const missingEditors = [...editorIds].filter((id) => !bundle.editors[id]);

  if (missingEditors.length === 0) {
    checksPassed.push(`All ${editorIds.size} editors present`);
  } else {
    checksFailed.push(`Missing ${missingEditors.length} editor(s)`);
  }

  // Determine result
  let result: VerificationResult['result'];
  if (checksFailed.length === 0) {
    result = 'VERIFIED';
  } else if (!hashesValid || !signaturesValid) {
    result = 'TAMPERED';
  } else {
    result = 'INCOMPLETE';
  }

  return {
    result,
    claimId: bundle._meta.claim_id,
    eventCount: bundle.events.length,
    checksPassed,
    checksFailed,
    warnings,
    details: {
      bundleVersion: bundle._meta.bundle_version,
      specVersion: bundle._meta.spec_version,
      exportedAt: bundle._meta.exported_at,
      chainValidAtExport: bundle._meta.chain_valid_at_export,
    },
  };
}

// ============================================================
// Component
// ============================================================

export function Verify() {
  const [isDragging, setIsDragging] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setResult(null);
    setFileName(file.name);
    setIsVerifying(true);

    try {
      const text = await file.text();
      const bundle = JSON.parse(text) as Bundle;
      const verificationResult = await verifyBundle(bundle);
      setResult(verificationResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to parse bundle');
    } finally {
      setIsVerifying(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);

      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith('.json')) {
        handleFile(file);
      } else {
        setError('Please drop a .json bundle file');
      }
    },
    [handleFile]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFile(file);
      }
    },
    [handleFile]
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800/50">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link
              to="/claims"
              className="flex items-center gap-2 text-slate-400 hover:text-slate-200"
            >
              <ArrowLeft className="w-5 h-5" />
              <span>Back to claims</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-4xl mx-auto px-4 py-12">
        {/* Hero */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center p-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 mb-6">
            <Shield className="w-10 h-10 text-emerald-400" />
          </div>
          <h1 className="text-3xl font-bold text-slate-100 mb-3">
            Independent Verification
          </h1>
          <p className="text-lg text-slate-400 max-w-xl mx-auto">
            Don't trust us. Verify it yourself.
            <br />
            Drop a claim bundle below to cryptographically verify its integrity.
          </p>
        </div>

        {/* Drop Zone */}
        <div
          className={`
            relative p-12 rounded-2xl border-2 border-dashed transition-all cursor-pointer
            ${
              isDragging
                ? 'border-emerald-500 bg-emerald-500/5'
                : 'border-slate-700 hover:border-slate-600 bg-slate-800/30'
            }
          `}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          <input
            id="file-input"
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleFileInput}
          />

          <div className="text-center">
            {isVerifying ? (
              <div className="animate-pulse">
                <Shield className="w-16 h-16 text-slate-500 mx-auto mb-4" />
                <p className="text-lg text-slate-400">Verifying...</p>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-center gap-3 mb-4">
                  <Upload className="w-8 h-8 text-slate-500" />
                  <FileJson className="w-8 h-8 text-slate-500" />
                </div>
                <p className="text-lg text-slate-300 mb-2">
                  Drop a bundle.json file here
                </p>
                <p className="text-sm text-slate-500">
                  or click to select a file
                </p>
              </>
            )}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mt-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center gap-3">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <p className="text-red-400">{error}</p>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="mt-8 space-y-6">
            {/* Verdict Banner */}
            <div
              className={`
                p-6 rounded-2xl border
                ${
                  result.result === 'VERIFIED'
                    ? 'bg-emerald-500/10 border-emerald-500/30'
                    : result.result === 'TAMPERED'
                    ? 'bg-red-500/10 border-red-500/30'
                    : 'bg-amber-500/10 border-amber-500/30'
                }
              `}
            >
              <div className="flex items-center gap-4">
                {result.result === 'VERIFIED' ? (
                  <CheckCircle className="w-12 h-12 text-emerald-400" />
                ) : result.result === 'TAMPERED' ? (
                  <XCircle className="w-12 h-12 text-red-400" />
                ) : (
                  <AlertTriangle className="w-12 h-12 text-amber-400" />
                )}
                <div>
                  <h2
                    className={`text-2xl font-bold ${
                      result.result === 'VERIFIED'
                        ? 'text-emerald-400'
                        : result.result === 'TAMPERED'
                        ? 'text-red-400'
                        : 'text-amber-400'
                    }`}
                  >
                    {result.result}
                  </h2>
                  <p className="text-slate-400">
                    {result.result === 'VERIFIED'
                      ? 'All cryptographic checks passed'
                      : result.result === 'TAMPERED'
                      ? 'Hash or signature mismatch detected'
                      : 'Missing required data for full verification'}
                  </p>
                </div>
              </div>
            </div>

            {/* Details Grid */}
            <div className="grid md:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50">
                <p className="text-sm text-slate-500 mb-1">Claim ID</p>
                <p className="font-mono text-sm text-slate-300 truncate">
                  {result.claimId}
                </p>
              </div>
              <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50">
                <p className="text-sm text-slate-500 mb-1">Events</p>
                <p className="text-slate-300">{result.eventCount}</p>
              </div>
              <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50">
                <p className="text-sm text-slate-500 mb-1">Bundle Version</p>
                <p className="text-slate-300">
                  {result.details.bundleVersion || 'N/A'}
                </p>
              </div>
              <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50">
                <p className="text-sm text-slate-500 mb-1">Spec Version</p>
                <p className="text-slate-300">
                  {result.details.specVersion || 'N/A'}
                </p>
              </div>
            </div>

            {/* Checks */}
            <div className="p-6 rounded-xl bg-slate-800/30 border border-slate-700/50">
              <h3 className="text-lg font-semibold text-slate-200 mb-4">
                Verification Checks
              </h3>

              {result.checksPassed.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-medium text-emerald-400 mb-2 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4" />
                    Passed
                  </h4>
                  <ul className="space-y-2">
                    {result.checksPassed.map((check, i) => (
                      <li
                        key={i}
                        className="flex items-center gap-2 text-sm text-slate-400"
                      >
                        {check.includes('hash') && <Hash className="w-4 h-4" />}
                        {check.includes('signature') && (
                          <Key className="w-4 h-4" />
                        )}
                        {check.includes('Chain') && (
                          <LinkIcon className="w-4 h-4" />
                        )}
                        {check.includes('editor') && (
                          <Users className="w-4 h-4" />
                        )}
                        {!check.includes('hash') &&
                          !check.includes('signature') &&
                          !check.includes('Chain') &&
                          !check.includes('editor') && (
                            <CheckCircle className="w-4 h-4" />
                          )}
                        <span>{check}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.checksFailed.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-medium text-red-400 mb-2 flex items-center gap-2">
                    <XCircle className="w-4 h-4" />
                    Failed
                  </h4>
                  <ul className="space-y-2">
                    {result.checksFailed.map((check, i) => (
                      <li
                        key={i}
                        className="flex items-center gap-2 text-sm text-red-400"
                      >
                        <XCircle className="w-4 h-4" />
                        <span>{check}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.warnings.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-amber-400 mb-2 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" />
                    Warnings
                  </h4>
                  <ul className="space-y-2">
                    {result.warnings.map((warning, i) => (
                      <li
                        key={i}
                        className="flex items-center gap-2 text-sm text-amber-400"
                      >
                        <AlertTriangle className="w-4 h-4" />
                        <span>{warning}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* File Info */}
            {fileName && (
              <p className="text-center text-sm text-slate-500">
                Verified: <span className="font-mono">{fileName}</span>
              </p>
            )}
          </div>
        )}

        {/* Info */}
        <div className="mt-12 p-6 rounded-xl bg-slate-800/20 border border-slate-800">
          <h3 className="font-semibold text-slate-300 mb-3">
            How Verification Works
          </h3>
          <ul className="space-y-2 text-sm text-slate-500">
            <li className="flex items-start gap-2">
              <Hash className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>
                <strong>Hash Verification</strong> — Each event's payload is
                canonicalized and hashed. The computed hash must match the
                stored hash.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <LinkIcon className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>
                <strong>Chain Linkage</strong> — Each event references the
                previous event's hash, creating a tamper-evident chain.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <Key className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>
                <strong>Signature Verification</strong> — Each event is signed
                by an editor using Ed25519. The signature must be valid.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <Users className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>
                <strong>Editor Validation</strong> — All editors who signed
                events must have their public keys included in the bundle.
              </span>
            </li>
          </ul>
        </div>
      </main>
    </div>
  );
}

