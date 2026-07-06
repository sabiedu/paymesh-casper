// x402 client handler for JS/TS — intercepts 402, signs a Casper payment,
// and retries with an X-PAYMENT header. Returns the resource + settlement receipt.
import { canonicalAuthorization, newNonce, signMessage, } from "./crypto.js";
const X_PAYMENT = "x-payment";
const X_PAYMENT_RESPONSE = "x-payment-response";
export class PaymentError extends Error {
}
function b64urlEncode(s) {
    const b64 = typeof btoa === "function"
        ? btoa(s)
        : Buffer.from(s, "utf-8").toString("base64");
    return b64.replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}
function b64urlDecodeToString(s) {
    const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
    const norm = (s + pad).replaceAll("-", "+").replaceAll("_", "/");
    return typeof atob === "function" ? atob(norm) : Buffer.from(norm, "base64").toString("utf-8");
}
function buildPayload(account, reqs) {
    const sender = account.publicAccountHex;
    const recipient = reqs.pay_to;
    const value = reqs.maxAmountRequired;
    const serviceId = String(reqs.metadata?.service_id ?? "");
    const nonce = newNonce();
    const authorization = canonicalAuthorization(sender, recipient, value, serviceId, nonce);
    // signature is filled in async by the caller (see x402Fetch)
    const inner = {
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
export async function x402Fetch(url, account, opts = {}) {
    const method = opts.method ?? "GET";
    const headers = { ...(opts.headers ?? {}) };
    const body = opts.jsonBody ? JSON.stringify(opts.jsonBody) : undefined;
    if (opts.jsonBody)
        headers["content-type"] = "application/json";
    let res = await fetch(url, { method, headers, body });
    let attempts = 0;
    while (res.status === 402 && attempts <= 1) {
        const challenge = (await res.clone().json().catch(() => null));
        const reqs = challenge?.accepts?.[0];
        if (!reqs)
            throw new PaymentError("server returned 402 with no payment requirements");
        const payload = buildPayload(account, reqs);
        payload.signature = await signMessage(payload.payload.authorization, account.privateKeyHex);
        headers[X_PAYMENT] = b64urlEncode(JSON.stringify(payload));
        res = await fetch(url, { method, headers, body });
        attempts++;
    }
    if (res.status === 402) {
        const ch = (await res.json().catch(() => null));
        throw new PaymentError(`payment rejected: ${ch?.error ?? "unknown"}`);
    }
    const data = (await res.json().catch(() => res.text()));
    let settlement = null;
    const receipt = res.headers.get(X_PAYMENT_RESPONSE);
    if (receipt) {
        try {
            settlement = JSON.parse(b64urlDecodeToString(receipt));
        }
        catch {
            settlement = null;
        }
    }
    return { status: res.status, data, settlement, requirements: null };
}
/** Helper used by PayMeshClient.callService to shape the result. */
export function toCallResult(serviceId, priceMotes, paid) {
    return {
        service_id: serviceId,
        data: paid.data,
        amount_paid_motes: priceMotes,
        settlement_id: paid.settlement?.transaction ?? "",
        success: Boolean(paid.settlement?.success),
    };
}
