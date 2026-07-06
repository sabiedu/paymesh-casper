# PayMesh JS/TS SDK

Typed SDK for the **x402 agent marketplace on Casper** — works in the browser
and in Node.

```ts
import { PayMeshClient, generateAccount } from "@paymesh/sdk";

const acct = await generateAccount("alice");
const pm = new PayMeshClient(acct, { nodeUrl: "http://127.0.0.1:8001" });

await pm.deposit(10);                                     // fund escrow (CSPR)
await pm.registerService("risk-api", "Risk API", "http://127.0.0.1:8002/risk", 0.05, 5);
await pm.stake("risk-api", 5);

const result = await pm.callService("risk-api");          // pays per-call via x402
await pm.rateService("risk-api", 5, "fast");
```

`callService` performs the full x402 handshake automatically: it receives the
`402 Payment Required` challenge, signs a payment with the account's Casper
Ed25519 key (via `@noble/ed25519`), settles through the facilitator, and retries
— returning the resource plus a settlement receipt.

## Build

```bash
cd sdk/js
npm install
npm run build      # emits dist/ (ESM + .d.ts)
```
