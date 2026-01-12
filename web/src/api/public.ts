/**
 * Public API
 * 
 * Read-only endpoints for public claim viewer.
 */

import { api } from './client';
import type { ClaimListItem, ClaimDetail, IntegrityStatus } from '../types';

export const publicApi = {
  /**
   * Get list of all claims.
   */
  getClaims: () => api.get<ClaimListItem[]>('/api/public/claims'),

  /**
   * Get full claim detail.
   */
  getClaim: (claimId: string) =>
    api.get<ClaimDetail>(`/api/public/claims/${claimId}`),

  /**
   * Export claim as markdown.
   */
  exportMarkdown: (claimId: string) =>
    api.get<{ markdown: string }>(`/api/public/claims/${claimId}/export.md`),

  /**
   * Get chain integrity status.
   */
  getIntegrity: () => api.get<IntegrityStatus>('/api/public/integrity'),
};

