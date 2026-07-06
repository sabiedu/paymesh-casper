// Thin API client that polls the PayMesh node REST endpoints.
// Set VITE_NODE_URL (or the form in the header) to point at a node/relayer.
// In live mode this can be swapped for CSPR.cloud / Casper RPC queries.

import type { MarketplaceStats, PaymentRecord, Review, ServiceInfo } from "./types";

const NODE_URL =
  (import.meta as any).env?.VITE_NODE_URL || "http://127.0.0.1:8001";

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
