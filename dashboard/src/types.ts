// Shared types for the PayMesh dashboard — mirror the SDK/node response shapes.

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
  reputation_score: number; // basis points of a star (0–50000)
  average_rating: number; // 0.0–5.0
  total_ratings: number;
  active: boolean;
  registered_at: number;
}

export interface PaymentRecord {
  index: number;
  payer: string;
  provider: string;
  service_id: string;
  amount_motes: number;
  payment_proof: string;
  timestamp: number;
}

export interface MarketplaceStats {
  service_count: number;
  active_services: number;
  total_staked_cspr: number;
  total_payments: number;
  total_volume_cspr: number;
  services: ServiceInfo[];
}

export interface Review {
  index: number;
  service_id: string;
  reviewer: string;
  rating: number;
  review: string;
  timestamp: number;
}

// ---- interactive marketplace types (provider form + x402 calls) ----

/** Body for `POST /registry/services`. */
export interface RegisterServicePayload {
  provider: string;
  service_id: string;
  name: string;
  endpoint: string;
  price_per_call_cspr: number;
  staking_amount_cspr: number;
  description?: string;
}

/** Body for `POST /registry/services/{id}/stake`. */
export interface StakePayload {
  provider: string;
  amount_cspr: number;
}

/** Body for `POST /registry/services/{id}/rate`. */
export interface RatePayload {
  reviewer: string;
  rating: number;
  review?: string;
}

/** Shape returned by `POST /agent/call` (a full x402 consumer flow). */
export interface AgentCallResult {
  success: boolean;
  data: Record<string, unknown> | null;
  amount_paid_cspr: number;
  settlement_id: string;
  consumer: string;
  service_id: string;
  error?: string;
}

/** A single step in the animated x402 payment flow. */
export type FlowStepState = "pending" | "active" | "done" | "error";

export interface FlowStep {
  id: string;
  label: string;
  tone: "neutral" | "danger" | "success";
  state: FlowStepState;
}

// ---------------------------------------------------------------------------
// Observability (/observe/metrics) types
// ---------------------------------------------------------------------------

export interface ObserveSummary {
  total_volume_cspr: number;
  total_payments: number;
  total_services: number;
  active_services: number;
  total_staked_cspr: number;
  avg_reputation: number;
  total_agents: number;
  uptime_seconds: number;
}

export interface VolumePoint {
  t: number;
  label: string;
  volume_cspr: number;
}

export interface ServiceVolume {
  service_id: string;
  name: string;
  call_count: number;
  volume_cspr: number;
}

export interface ReputationRow {
  service_id: string;
  name: string;
  rating: number;
  ratings_count: number;
}

export interface DeployedContract {
  name: string;
  description: string;
  package_hash: string;
  deploy_hash: string;
  status: string;
}

export interface AgentRow {
  address: string;
  role: string;
  is_provider: boolean;
  is_consumer: boolean;
  services_offered: number;
  stake_cspr: number;
  paid_cspr: number;
  reputation: number;
  last_active: number;
}

export interface NetworkInfo {
  network: string;
  chain_name: string;
  protocol: string;
  rpc_status: string;
  explorer_url: string;
  current_node: string;
  generated_at: number;
}

export interface ObserveMetrics {
  summary: ObserveSummary;
  volume_timeseries: VolumePoint[];
  payments_per_service: ServiceVolume[];
  reputation_breakdown: ReputationRow[];
  contracts: DeployedContract[];
  agent_registry: AgentRow[];
  network: NetworkInfo;
}

