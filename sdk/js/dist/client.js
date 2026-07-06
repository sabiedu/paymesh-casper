// PayMeshClient — the typed entry point for the agent marketplace (JS/TS).
//
//   import { PayMeshClient, generateAccount } from "@paymesh/sdk";
//
//   const acct = await generateAccount("alice");
//   const pm = new PayMeshClient(acct, { nodeUrl: "http://127.0.0.1:8001" });
//   await pm.deposit(10);
//   await pm.registerService("risk-api", "Risk API", "http://…/risk", 0.05, 5);
//   await pm.stake("risk-api", 5);
//   const result = await pm.callService("risk-api");   // pays per-call via x402
//   await pm.rateService("risk-api", 5, "great");
import { HttpContractBackend } from "./backend.js";
import { toCallResult, x402Fetch } from "./x402.js";
export class PayMeshClient {
    constructor(account, opts = {}) {
        this.account = account;
        this.backend =
            opts.backend ?? new HttpContractBackend(opts.nodeUrl ?? "http://127.0.0.1:8001");
        this.facilitatorUrl = (opts.facilitatorUrl ?? opts.nodeUrl ?? "http://127.0.0.1:8001").replace(/\/$/, "");
    }
    get address() {
        return this.account.publicAccountHex;
    }
    // --- escrow balance ---
    async deposit(amountCspr) {
        await this.backend.deposit(this.address, amountCspr);
    }
    async balance() {
        return this.backend.balance(this.address);
    }
    // --- ServiceRegistry ---
    async registerService(serviceId, name, endpoint, pricePerCall, stakeAmount) {
        await this.backend.registerService(this.address, serviceId, name, endpoint, pricePerCall, stakeAmount);
        return this.backend.getService(serviceId);
    }
    async discoverServices(category) {
        const services = await this.backend.listServices(true);
        if (category) {
            const q = category.toLowerCase();
            return services.filter((s) => s.name.toLowerCase().includes(q));
        }
        return services;
    }
    async getService(serviceId) {
        return this.backend.getService(serviceId);
    }
    async stake(serviceId, amountCspr) {
        await this.backend.stake(this.address, serviceId, amountCspr);
    }
    // --- x402 paid call ---
    async callService(serviceId, kwargs = {}) {
        const svc = await this.backend.getService(serviceId);
        if (!svc)
            throw new Error(`unknown service ${serviceId}`);
        if (!svc.active)
            throw new Error(`service ${serviceId} is not active`);
        const paid = await x402Fetch(svc.endpoint, this.account, {
            method: Object.keys(kwargs).length ? "POST" : "GET",
            jsonBody: Object.keys(kwargs).length ? kwargs : undefined,
        });
        return toCallResult(serviceId, svc.price_per_call_motes, paid);
    }
    // --- Reputation ---
    async rateService(serviceId, rating, review = "") {
        await this.backend.rate(this.address, serviceId, rating, review);
        return this.backend.getReputation(serviceId);
    }
    async getReputation(serviceId) {
        return this.backend.getReputation(serviceId);
    }
}
