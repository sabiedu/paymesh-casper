import { Account } from "./crypto.js";
import { CallResult, PaymentRequirements, SettleResponse } from "./types.js";
export declare class PaymentError extends Error {
}
export interface PaidResponse<T = any> {
    status: number;
    data: T;
    settlement: SettleResponse | null;
    requirements: PaymentRequirements | null;
}
export declare function x402Fetch<T = any>(url: string, account: Account, opts?: {
    method?: string;
    jsonBody?: any;
    headers?: Record<string, string>;
    timeoutMs?: number;
}): Promise<PaidResponse<T>>;
/** Helper used by PayMeshClient.callService to shape the result. */
export declare function toCallResult(serviceId: string, priceMotes: number, paid: PaidResponse): CallResult;
