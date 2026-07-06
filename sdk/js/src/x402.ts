// x402 client handler for JS/TS — intercepts 402, signs a Casper payment,
// and retries with an X-PAYMENT header. Returns the resource + settlement receipt.

import {
  Account,
  canonicalAuthorization,
  newNonce,
  signMessage,
} from "./crypto.js";
import {
  CallResult,
  PaymentPayload,
  PaymentPayloadInner,
  PaymentRequirements,
  SettleResponse,
} from "./types.js";

const X_PAYMENT = "x-payment";
const X_PAYMENT_RESPONSE = "x-payment-response";

export class PaymentError extends Error {}

export interface PaidResponse<T = any> {
  status: number;
  data: T;
  settlement: SettleResponse | null;
  requirements: PaymentRequirements | null;
}

function b64urlEncode(s: string): string {
  const b64 = typeof btoa === "function"
    ? btoa(s)
    : Buffer.from(s, "utf-8").toString("base64");
  return b64.replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function b64urlDecodeToString(s: string): string {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const norm = (s + pad).replaceAll("-", "+").replaceAll("_", "/");
  return typeof atob === "function" ? atob(norm) : Buffer.from(norm, "base64").toString("utf-8");
}

function buildPayload(
  account: Account,
  reqs: PaymentRequirements
): PaymentPayload {
  const sender = account.publicAccountHex;
  const recipient = reqs.pay_to;
  const value = reqs.maxAmountRequired;
  const serviceId = String((reqs.metadata as any)?.service_id ?? "");
  const nonce = newNonce();
  const authorization = canonicalAuthorization(sender, recipient, value, serviceId, nonce);
  // signature is filled in async by the caller (see x402Fetch)
  const inner: PaymentPayloadInner = {
    from: sender,
    to: recipient,
    value,
    service_id: serviceId,
    nonce,
    authorization,
  };
  return {
    x402_version: 1,
    scheme: reqs.scheme,
    network: reqs.network,
    payload: inner,
    signature: "",
  };
}

export async function x402Fetch<T = any>(
  url: string,
  account: Account,
  opts: { method?: string; jsonBody?: any; headers?: Record<string, string>; timeoutMs?: number } = {}
): Promise<PaidResponse<T>> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  const body = opts.jsonBody ? JSON.stringify(opts.jsonBody) : undefined;
  if (opts.jsonBody) headers["content-type"] = "application/json";

  let res = await fetch(url, { method, headers, body });

  let attempts = 0;
  while (res.status === 402 && attempts <= 1) {
    const challenge = (await res.clone().json().catch(() => null)) as
      | { accepts?: PaymentRequirements[]; error?: string }
      | null;
    const reqs = challenge?.accepts?.[0];
    if (!reqs) throw new PaymentError("server returned 402 with no payment requirements");

    const payload = buildPayload(account, reqs);
    payload.signature = await signMessage(payload.payload.authorization, account.privateKeyHex);
    headers[X_PAYMENT] = b64urlEncode(JSON.stringify(payload));
    res = await fetch(url, { method, headers, body });
    attempts++;
  }

  if (res.status === 402) {
    const ch = (await res.json().catch(() => null)) as { error?: string } | null;
    throw new PaymentError(`payment rejected: ${ch?.error ?? "unknown"}`);
  }

  const data = (await res.json().catch(() => res.text())) as T;
  let settlement: SettleResponse | null = null;
  const receipt = res.headers.get(X_PAYMENT_RESPONSE);
  if (receipt) {
    try {
      settlement = JSON.parse(b64urlDecodeToString(receipt)) as SettleResponse;
    } catch {
      settlement = null;
    }
  }
  return { status: res.status, data, settlement, requirements: null };
}

/** Helper used by PayMeshClient.callService to shape the result. */
export function toCallResult(
  serviceId: string,
  priceMotes: number,
  paid: PaidResponse
): CallResult {
  return {
    service_id: serviceId,
    data: paid.data,
    amount_paid_motes: priceMotes,
    settlement_id: paid.settlement?.transaction ?? "",
    success: Boolean(paid.settlement?.success),
  };
}
