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
