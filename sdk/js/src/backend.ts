// HTTP contract backend — talks to a PayMesh marketplace node (x402.node)
// over fetch. Mirrors the Python HttpContractBackend.

import { csprToMotes, motesToCspr, ServiceInfo } from "./types.js";

export class HttpContractBackend {
  constructor(public nodeUrl: string, public timeoutMs = 15000) {
    this.nodeUrl = nodeUrl.replace(/\/$/, "");
  }

  private async get<T>(path: string, params?: Record<string, string>): Promise<T | null> {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    const res = await fetch(`${this.nodeUrl}${path}${qs}`, {
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`${path} -> ${res.status}`);
    return (await res.json()) as T;
  }

  private async post<T>(path: string, body: any): Promise<T> {
    const res = await fetch(`${this.nodeUrl}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!res.ok) throw new Error(`${path} -> ${res.status}: ${await res.text()}`);
    return (await res.json()) as T;
  }

  async registerService(
    provider: string,
    serviceId: string,
    name: string,
    endpoint: string,
    pricePerCallCspr: number,
    stakingAmountCspr: number
  ): Promise<void> {
    await this.post("/registry/services", {
      provider,
      service_id: serviceId,
      name,
      endpoint,
      price_per_call_cspr: pricePerCallCspr,
      staking_amount_cspr: stakingAmountCspr,
    });
  }

  async stake(provider: string, serviceId: string, amountCspr: number): Promise<void> {
    await this.post(`/registry/services/${encodeURIComponent(serviceId)}/stake`, {
      provider,
      amount_cspr: amountCspr,
    });
  }

  async listServices(activeOnly = true): Promise<ServiceInfo[]> {
    const data = await this.get<{ services: ServiceInfo[] }>("/registry/services", {
      active_only: String(activeOnly),
    });
    return data?.services ?? [];
  }

  async getService(serviceId: string): Promise<ServiceInfo | null> {
    return this.get<ServiceInfo>(`/registry/services/${encodeURIComponent(serviceId)}`);
  }

  async rate(reviewer: string, serviceId: string, rating: number, review: string) {
    return this.post(`/registry/services/${encodeURIComponent(serviceId)}/rate`, {
      reviewer,
      rating,
      review,
    });
  }

  async getReputation(serviceId: string) {
    return this.get<{ count: number; average_rating: number; reputation_score: number }>(
      `/registry/services/${encodeURIComponent(serviceId)}/reputation`
    );
  }

  async deposit(account: string, amountCspr: number) {
    return this.post<{ ok: boolean; balance_cspr: number }>("/registry/deposit", {
      account,
      amount_cspr: amountCspr,
    });
  }

  async balance(account: string): Promise<number> {
    const data = await this.get<{ balance_motes: number }>(`/balances/${account}`);
    return motesToCspr(data?.balance_motes ?? 0);
  }
}
