import { Account } from "./crypto.js";
import { HttpContractBackend } from "./backend.js";
import { CallResult, ReputationAggregate, ServiceInfo } from "./types.js";
export interface PayMeshClientOptions {
    nodeUrl?: string;
    facilitatorUrl?: string;
    backend?: HttpContractBackend;
}
export declare class PayMeshClient {
    readonly account: Account;
    readonly backend: HttpContractBackend;
    readonly facilitatorUrl: string;
    constructor(account: Account, opts?: PayMeshClientOptions);
    get address(): string;
    deposit(amountCspr: number): Promise<void>;
    balance(): Promise<number>;
    registerService(serviceId: string, name: string, endpoint: string, pricePerCall: number, stakeAmount: number): Promise<ServiceInfo | null>;
    discoverServices(category?: string): Promise<ServiceInfo[]>;
    getService(serviceId: string): Promise<ServiceInfo | null>;
    stake(serviceId: string, amountCspr: number): Promise<void>;
    callService(serviceId: string, kwargs?: Record<string, unknown>): Promise<CallResult>;
    rateService(serviceId: string, rating: number, review?: string): Promise<ReputationAggregate | null>;
    getReputation(serviceId: string): Promise<ReputationAggregate | null>;
}
