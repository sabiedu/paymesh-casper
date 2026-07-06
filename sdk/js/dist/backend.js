// HTTP contract backend — talks to a PayMesh marketplace node (x402.node)
// over fetch. Mirrors the Python HttpContractBackend.
import { motesToCspr } from "./types.js";
export class HttpContractBackend {
    constructor(nodeUrl, timeoutMs = 15000) {
        this.nodeUrl = nodeUrl;
        this.timeoutMs = timeoutMs;
        this.nodeUrl = nodeUrl.replace(/\/$/, "");
    }
    async get(path, params) {
        const qs = params ? "?" + new URLSearchParams(params).toString() : "";
        const res = await fetch(`${this.nodeUrl}${path}${qs}`, {
            signal: AbortSignal.timeout(this.timeoutMs),
        });
        if (res.status === 404)
            return null;
        if (!res.ok)
            throw new Error(`${path} -> ${res.status}`);
        return (await res.json());
    }
    async post(path, body) {
        const res = await fetch(`${this.nodeUrl}${path}`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(this.timeoutMs),
        });
        if (!res.ok)
            throw new Error(`${path} -> ${res.status}: ${await res.text()}`);
        return (await res.json());
    }
    async registerService(provider, serviceId, name, endpoint, pricePerCallCspr, stakingAmountCspr) {
        await this.post("/registry/services", {
            provider,
            service_id: serviceId,
            name,
            endpoint,
            price_per_call_cspr: pricePerCallCspr,
            staking_amount_cspr: stakingAmountCspr,
        });
    }
    async stake(provider, serviceId, amountCspr) {
        await this.post(`/registry/services/${encodeURIComponent(serviceId)}/stake`, {
            provider,
            amount_cspr: amountCspr,
        });
    }
    async listServices(activeOnly = true) {
        const data = await this.get("/registry/services", {
            active_only: String(activeOnly),
        });
        return data?.services ?? [];
    }
    async getService(serviceId) {
        return this.get(`/registry/services/${encodeURIComponent(serviceId)}`);
    }
    async rate(reviewer, serviceId, rating, review) {
        return this.post(`/registry/services/${encodeURIComponent(serviceId)}/rate`, {
            reviewer,
            rating,
            review,
        });
    }
    async getReputation(serviceId) {
        return this.get(`/registry/services/${encodeURIComponent(serviceId)}/reputation`);
    }
    async deposit(account, amountCspr) {
        return this.post("/registry/deposit", {
            account,
            amount_cspr: amountCspr,
        });
    }
    async balance(account) {
        const data = await this.get(`/balances/${account}`);
        return motesToCspr(data?.balance_motes ?? 0);
    }
}
