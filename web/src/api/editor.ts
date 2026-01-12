/**
 * Editor API
 * 
 * Authentication and command endpoints for editor portal.
 */

import { api } from './client';
import type {
  LoginRequest,
  LoginResponse,
  MeResponse,
  DeclareRequest,
  OperationalizeRequest,
  EvidenceRequest,
  ResolveRequest,
  EventResponse,
  EditorClaimListItem,
} from '../types';

export const editorApi = {
  // ============================================================
  // Auth
  // ============================================================

  /**
   * Login and get session cookie.
   */
  login: (credentials: LoginRequest) =>
    api.post<LoginResponse>('/api/editor/login', credentials),

  /**
   * Logout and clear session.
   */
  logout: () => api.post<{ success: boolean }>('/api/editor/logout'),

  /**
   * Get current editor info.
   */
  me: () => api.get<MeResponse>('/api/editor/me'),

  /**
   * Get list of claims for editor dashboard.
   */
  getClaims: () => api.get<EditorClaimListItem[]>('/api/editor/claims'),

  // ============================================================
  // Commands
  // ============================================================

  /**
   * Declare a new claim.
   */
  declareClaim: (data: DeclareRequest) =>
    api.post<EventResponse>('/api/editor/claims/declare', data),

  /**
   * Operationalize a claim.
   */
  operationalizeClaim: (claimId: string, data: Omit<OperationalizeRequest, 'claim_id'>) =>
    api.post<EventResponse>(`/api/editor/claims/${claimId}/operationalize`, {
      ...data,
      claim_id: claimId,
    }),

  /**
   * Add evidence to a claim.
   */
  addEvidence: (claimId: string, data: Omit<EvidenceRequest, 'claim_id'>) =>
    api.post<EventResponse>(`/api/editor/claims/${claimId}/evidence`, {
      ...data,
      claim_id: claimId,
    }),

  /**
   * Resolve a claim.
   */
  resolveClaim: (claimId: string, data: Omit<ResolveRequest, 'claim_id'>) =>
    api.post<EventResponse>(`/api/editor/claims/${claimId}/resolve`, {
      ...data,
      claim_id: claimId,
    }),
};

