// Thin API client that polls the PayMesh node REST endpoints.
// Set VITE_NODE_URL (or the form in the header) to point at a node/relayer.
// In live mode this can be swapped for CSPR.cloud / Casper RPC queries.

import type { AgentCallResult, MarketplaceStats, ObserveMetrics, PaymentRecord, RatePayload, RegisterServicePayload, Review, ServiceInfo, StakePayload } from "./types";

// Default to "" (relative) so the Vite proxy handles API calls on the same origin.
// This means remote visitors get the API transparently on the same origin.
// To point at a different node, set VITE_NODE_URL or use the "Connect" form.
const NODE_URL =
  (import.meta as any).env?.VITE_NODE_URL || "";

let baseUrl = NODE_URL.replace(/\/$/, "");

export function setBaseUrl(url: string) {
  baseUrl = url.replace(/\/$/, "");
}
export function getBaseUrl() {
  return baseUrl;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${baseUrl}${path}`, { signal: AbortSignal.timeout(8000) });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(45000),
  });
  if (!res.ok) {
    let detail = `${path} -> ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* keep status detail */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export async function fetchStats(): Promise<MarketplaceStats> {
  return getJson<MarketplaceStats>("/registry/stats");
}

export async function fetchServices(): Promise<ServiceInfo[]> {
  const data = await getJson<{ services: ServiceInfo[] }>("/registry/services");
  return data.services ?? [];
}

export async function fetchRecentPayments(limit = 25): Promise<PaymentRecord[]> {
  const data = await getJson<{ payments: PaymentRecord[] }>(
    `/recent_payments?limit=${limit}`
  );
  return data.payments ?? [];
}

export async function fetchReviews(serviceId: string): Promise<Review[]> {
  const data = await getJson<{ reviews: Review[] }>(
    `/registry/services/${encodeURIComponent(serviceId)}/reviews`
  );
  return data.reviews ?? [];
}

export async function checkHealth(): Promise<boolean> {
  try {
    const r = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(4000) });
    return r.ok;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Observability — aggregated analytics
// ---------------------------------------------------------------------------

export async function fetchObserveMetrics(): Promise<ObserveMetrics> {
  return getJson<ObserveMetrics>("/observe/metrics");
}

// ---------------------------------------------------------------------------
// Demo Console — interactive agent lifecycle endpoints
// ---------------------------------------------------------------------------

export interface DemoActivityEvent {
  id: number;
  ts: number;
  type: "provider" | "consumer" | "payment" | "settlement" | "rating" | "discover" | "system";
  icon: string;
  message: string;
  run_id: string | null;
}

export interface RegisteredService {
  service_id: string;
  name: string;
  emoji: string;
  tag: string;
  price_cspr: number;
  stake_cspr: number;
  provider: string;
  endpoint: string;
  run_id: string;
}

export interface ConsumerCallResult {
  service_id: string;
  success: boolean;
  amount_paid_cspr?: number;
  settlement_id?: string;
  data?: Record<string, unknown>;
  wallet?: string;
  rating?: number;
  reputation?: number;
  rating_count?: number;
  run_id: string;
  error?: string;
}

export interface FlowCall {
  success: boolean;
  amount_cspr: number;
  settlement_id?: string;
  summary: string;
}

export interface FullFlowResult {
  run_id: string;
  service: RegisteredService;
  calls: FlowCall[];
  total_volume_cspr: number;
  events: DemoActivityEvent[];
}

/** Generate + register + stake a random provider service. */
export async function demoRegisterProvider(): Promise<RegisteredService> {
  return postJson<RegisteredService>("/demo/register-provider");
}

/** Launch a consumer agent and make one real x402 paid call. */
export async function demoConsumerCall(serviceId: string, wallet?: string): Promise<ConsumerCallResult> {
  return postJson<ConsumerCallResult>("/demo/consumer-call", { service_id: serviceId, wallet });
}

/** One-click full lifecycle (register → stake → 3-4 calls → rate). */
export async function demoRunFullFlow(): Promise<FullFlowResult> {
  return postJson<FullFlowResult>("/demo/run-full-flow");
}

/** Live activity log (optionally only events newer than `sinceId`). */
export async function fetchActivity(sinceId = 0): Promise<DemoActivityEvent[]> {
  const data = await getJson<{ events: DemoActivityEvent[] }>(`/demo/activity?since_id=${sinceId}&limit=200`);
  return data.events ?? [];
}

// ---- write helpers (interactive marketplace) ----

/** Register a new paid service on the marketplace. */
export async function registerService(payload: RegisterServicePayload): Promise<ServiceInfo> {
  return postJson<ServiceInfo>("/registry/services", payload);
}

/** Stake CSPR behind a service (activates it once the minimum is met). */
export async function stakeService(serviceId: string, payload: StakePayload): Promise<ServiceInfo> {
  return postJson<ServiceInfo>(
    `/registry/services/${encodeURIComponent(serviceId)}/stake`,
    payload
  );
}

/** Rate a service 1–5 after using it. */
export async function rateService(
  serviceId: string,
  payload: RatePayload
): Promise<{ count: number; average_rating: number }> {
  return postJson(
    `/registry/services/${encodeURIComponent(serviceId)}/rate`,
    payload
  );
}

/** Run a full x402 consumer paid call server-side (402 → pay → 200 → settle). */
export async function callService(
  serviceId: string,
  wallet?: string
): Promise<AgentCallResult> {
  const body: { service_id: string; wallet?: string } = { service_id: serviceId };
  if (wallet && wallet.trim()) body.wallet = wallet.trim();
  return postJson<AgentCallResult>("/agent/call", body);
}
