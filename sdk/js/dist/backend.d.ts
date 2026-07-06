import { ServiceInfo } from "./types.js";
export declare class HttpContractBackend {
    nodeUrl: string;
    timeoutMs: number;
    constructor(nodeUrl: string, timeoutMs?: number);
    private get;
    private post;
    registerService(provider: string, serviceId: string, name: string, endpoint: string, pricePerCallCspr: number, stakingAmountCspr: number): Promise<void>;
    stake(provider: string, serviceId: string, amountCspr: number): Promise<void>;
    listServices(activeOnly?: boolean): Promise<ServiceInfo[]>;
    getService(serviceId: string): Promise<ServiceInfo | null>;
    rate(reviewer: string, serviceId: string, rating: number, review: string): Promise<unknown>;
    getReputation(serviceId: string): Promise<{
        count: number;
        average_rating: number;
        reputation_score: number;
    } | null>;
    deposit(account: string, amountCspr: number): Promise<{
        ok: boolean;
        balance_cspr: number;
    }>;
    balance(account: string): Promise<number>;
}
