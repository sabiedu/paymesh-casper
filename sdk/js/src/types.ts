// Shared types for the PayMesh JS/TS SDK — mirror the Python SDK shapes.

export const MOTES_PER_CSPR = 1_000_000_000;

export function motesToCspr(motes: number | string): number {
  return Number(motes) / MOTES_PER_CSPR;
}
export function csprToMotes(cspr: number): number {
  return Math.floor(cspr * MOTES_PER_CSPR);
}

export interface ServiceInfo {
  service_id: string;
  provider: string;
  name: string;
  endpoint: string;
  price_per_call_motes: number;
  price_per_call_cspr: number;
  staking_amount_motes: number;
  staking_amount_cspr: number;
  stake_amount_cspr?: number;
  reputation_score: number;
  average_rating: number;
  total_ratings: number;
  active: boolean;
  registered_at: number;
}

export interface ReputationAggregate {
  count: number;
  average_rating: number;
  reputation_score: number;
}

export interface Review {
  index: number;
  service_id: string;
  reviewer: string;
  rating: number;
  review: string;
  timestamp: number;
}

export interface CallResult {
  service_id: string;
  data: any;
  amount_paid_motes: number;
  settlement_id: string;
  success: boolean;
}

// ---- x402 wire types ----
export interface PaymentRequirements {
  scheme: string;
  network: string;
  x402_network?: string;
  asset: string;
  maxAmountRequired: string;
  resource: string;
  description?: string;
  pay_to: string;
  mimeType?: string;
  created?: number;
  expires?: number;
  metadata?: Record<string, unknown>;
}

export interface PaymentPayloadInner {
  from: string;
  to: string;
  value: string;
  service_id: string;
  nonce: string;
  authorization: string;
}

export interface PaymentPayload {
  x402_version: number;
  scheme: string;
  network: string;
  payload: PaymentPayloadInner;
  signature: string;
}

export interface SettleResponse {
  success: boolean;
  network: string;
  transaction: string;
  payer: string;
  payee: string;
  error?: string;
}
