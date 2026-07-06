# SDK Guide

PayMesh ships **two typed SDKs** — Python and TypeScript/JavaScript — with a near
identical API surface. Both hide the x402 payment complexity behind a single
object: `PayMeshClient`.

```
sdk/
├── python/paymesh/
│   ├── client.py          # PayMeshClient — the typed entry point
│   ├── backends.py        # Local + Casper + Http backends (same interface)
│   ├── casper_client.py   # direct Casper RPC client
│   └── models.py          # ServiceInfo, StakeInfo, CallResult, …
└── js/src/
    ├── client.ts          # PayMeshClient
    ├── backend.ts         # HttpContractBackend
    ├── crypto.ts          # Ed25519 accounts (@noble/ed25519)
    ├── x402.ts            # x402Fetch
    └── types.ts           # shared TS interfaces
```

> Both SDKs accept monetary amounts in **CSPR** (floats); the SDK converts to
> motes internally (1 CSPR = 10⁹ motes).

---

## Python SDK

### Install

```bash
pip install -e sdk/python
```

Requires Python ≥ 3.10. Dependencies: `fastapi`, `uvicorn`, `requests`, `pydantic`,
`cryptography`.

### Initialize

```python
from paymesh import PayMeshClient, generate_account

# Fresh Casper Ed25519 identity
account = generate_account("alice")

# Default backend is LocalContractBackend (offline simulation).
pm = PayMeshClient(
    account=account,
    facilitator_url="http://127.0.0.1:8001",
)
```

Point at a running node over HTTP instead:

```python
from paymesh import HttpContractBackend

pm = PayMeshClient(
    account=account,
    backend=HttpContractBackend("http://127.0.0.1:8001"),
    facilitator_url="http://127.0.0.1:8001",
)
```

Or restore an identity from a stored private key:

```python
from paymesh import account_from_private_key
account = account_from_private_key("abcd1234...64hexbytes", "alice")
```

### `PayMeshClient` method reference

#### Identity

| Method | Returns | Description |
|--------|---------|-------------|
| `.address` | `str` | the caller's `01…` Casper account hex |

#### Escrow (Settlement layer)

| Method | Returns | Description |
|--------|---------|-------------|
| `deposit(amount_cspr)` | `None` | fund the caller's escrow balance |
| `balance()` | `float` | available CSPR in escrow |
| `revenue()` | `float` | lifetime CSPR earned as a provider |

#### ServiceRegistry

| Method | Returns | Description |
|--------|---------|-------------|
| `register_service(id, name, endpoint, price_per_call, stake_amount)` | `ServiceInfo` | publish a service (CSPR units) |
| `deregister_service(id)` | `None` | take a service down |
| `discover_services(category=None, active_only=True)` | `list[ServiceInfo]` | list / filter services |
| `get_service(id)` | `ServiceInfo \| None` | read one |

#### Staking

| Method | Returns | Description |
|--------|---------|-------------|
| `stake(id, amount_cspr)` | `None` | lock CSPR (activates once min met) |
| `get_stake(id)` | `StakeInfo \| None` | read the stake record |

#### x402 paid call

| Method | Returns | Description |
|--------|---------|-------------|
| `call_service(id, **kwargs)` | `CallResult` | call a service, paying per-call via x402 |

#### Reputation

| Method | Returns | Description |
|--------|---------|-------------|
| `rate_service(id, rating, review="")` | `ReputationAggregate` | rate 1–5 |
| `get_reputation(id)` | `ReputationAggregate` | running aggregate |
| `get_reviews(id)` | `list[Review]` | all reviews |

---

### Full example: provider + consumer

**Provider flow** — register, stake, serve:

```python
from paymesh import PayMeshClient, generate_account

provider = generate_account("risk-provider")
pm = PayMeshClient(account=provider, facilitator_url="http://127.0.0.1:8001")

# 1. Register the service (0.05 CSPR / call, 5 CSPR declared stake)
pm.register_service(
    "risk-score-api",
    "Risk Score API",
    "http://127.0.0.1:8002/risk",
    price_per_call=0.05,
    stake_amount=5.0,
)

# 2. Lock the stake — this activates the service
pm.stake("risk-score-api", 5.0)

print(pm.get_service("risk-score-api").active)  # True
print(f"provider revenue so far: {pm.revenue()} CSPR")
```

**Consumer flow** — discover, call, rate:

```python
from paymesh import PayMeshClient, generate_account, HttpContractBackend

consumer = generate_account("alice")
pm = PayMeshClient(
    account=consumer,
    backend=HttpContractBackend("http://127.0.0.1:8001"),
    facilitator_url="http://127.0.0.1:8001",
)

# 1. Fund escrow so the facilitator can settle per-call payments
pm.deposit(10.0)

# 2. Discover what's available
for svc in pm.discover_services():
    print(f"  {svc.service_id:20s} {svc.price_per_call_cspr:.4f} CSPR  {'★'*round(svc.average_rating)}")

# 3. Call a service — the SDK handles the x402 402 → sign → 200 flow
result = pm.call_service("risk-score-api", wallet="0xabc123...")
print("score:", result.data, "| paid:", result.amount_paid_motes / 1e9, "CSPR")
print("settlement:", result.settlement_id)

# 4. Rate it
agg = pm.rate_service("risk-score-api", 5, "fast & accurate")
print(f"new average: {agg.average_rating:.2f} over {agg.count} ratings")
```

### Data models (`models.py`)

```python
@dataclass
class ServiceInfo:
    service_id: str
    provider: str
    name: str
    endpoint: str
    price_per_call_motes: int
    staking_amount_motes: int
    reputation_score: int       # basis points of a star (0–50000)
    total_ratings: int
    active: bool
    registered_at: int

    @property
    def price_per_call_cspr(self) -> float: ...
    @property
    def staking_amount_cspr(self) -> float: ...
    @property
    def average_rating(self) -> float: ...   # 0.0–5.0
    def to_dict(self) -> dict: ...

@dataclass
class CallResult:
    service_id: str
    data: object
    amount_paid_motes: int
    settlement_id: str
    success: bool = True
```

### Error handling

```python
from paymesh import PayMeshClient, generate_account

pm = PayMeshClient(account=generate_account("alice"), facilitator_url="http://127.0.0.1:8001")

try:
    result = pm.call_service("does-not-exist")
except KeyError as e:
    print(f"unknown service: {e}")          # service not registered

try:
    result = pm.call_service("unstaked-api")
except RuntimeError as e:
    print(f"service inactive: {e}")         # stake it first
```

`call_service` raises:
- `KeyError` — the `service_id` is not registered.
- `RuntimeError` — the service exists but is not `active` (stake it first).
- `x402.client.PaymentError` — the provider rejected payment or no usable
  requirements were returned.

`success` on the returned `CallResult` is `False` if the endpoint responded `200`
without triggering an x402 settlement (e.g. a misconfigured provider).

### Backends

All three backends implement the same `ContractBackend` interface:

```python
from paymesh.backends import (
    LocalContractBackend,     # in-process simulation (default, offline)
    CasperContractBackend,    # live Casper testnet over RPC
)
from paymesh import HttpContractBackend   # a running PayMesh node over REST
```

> **Swap demo ↔ testnet** by passing a different `backend=`. The agent code is
> unchanged. `LocalContractBackend` mirrors the on-chain contract semantics
> exactly, including the staking requirement and one-rating-per-(reviewer,service).

---

## TypeScript / JavaScript SDK

### Install

```bash
cd sdk/js
npm install
npm run build      # emits dist/
```

Then in your project:

```bash
npm install ../paymesh-casper/sdk/js   # local path
# or, once published:  npm install @paymesh/sdk
```

Dependencies: `@noble/ed25519`, `@noble/hashes`. Works in Node and the browser
(the dashboard bundles it). Requires Node ≥ 18.

### Initialize

```typescript
import { PayMeshClient, generateAccount } from "@paymesh/sdk";

const account = await generateAccount("alice");
const pm = new PayMeshClient(account, {
  nodeUrl: "http://127.0.0.1:8001",
});
```

Restore from a stored key:

```typescript
import { accountFromPrivateKey } from "@paymesh/sdk";
const account = await accountFromPrivateKey("abcd1234...64hex", "alice");
```

### `PayMeshClient` method reference (async)

| Method | Returns | Description |
|--------|---------|-------------|
| `get address` | `string` | caller's `01…` account hex |
| `deposit(amountCspr)` | `Promise<void>` | fund escrow |
| `balance()` | `Promise<number>` | CSPR in escrow |
| `registerService(id, name, endpoint, price, stake)` | `Promise<ServiceInfo>` | publish + return it |
| `discoverServices(category?)` | `Promise<ServiceInfo[]>` | list / filter |
| `getService(id)` | `Promise<ServiceInfo \| null>` | read one |
| `stake(id, amountCspr)` | `Promise<void>` | lock CSPR |
| `callService(id, kwargs?)` | `Promise<CallResult>` | x402 paid call |
| `rateService(id, rating, review?)` | `Promise<ReputationAggregate>` | rate 1–5 |

### Full example

```typescript
import { PayMeshClient, generateAccount } from "@paymesh/sdk";

// ---- Provider ----
const provider = await generateAccount("risk-provider");
const pmp = new PayMeshClient(provider, { nodeUrl: "http://127.0.0.1:8001" });

const svc = await pmp.registerService(
  "risk-score-api",
  "Risk Score API",
  "http://127.0.0.1:8002/risk",
  0.05,   // CSPR / call
  5.0,    // CSPR stake
);
await pmp.stake("risk-score-api", 5.0);
console.log("active?", svc.active);

// ---- Consumer ----
const consumer = await generateAccount("alice");
const pm = new PayMeshClient(consumer, { nodeUrl: "http://127.0.0.1:8001" });

await pm.deposit(10);
const services = await pm.discoverServices();
services.forEach((s) => console.log(s.service_id, s.price_per_call_cspr));

const result = await pm.callService("risk-score-api", { wallet: "0xabc123" });
console.log("score:", result.data, "settled:", result.settlement_id);

const agg = await pm.rateService("risk-score-api", 5, "fast & accurate");
console.log(`avg ${agg.average_rating.toFixed(2)} over ${agg.count}`);
```

### Error handling

```typescript
try {
  await pm.callService("does-not-exist");
} catch (e: any) {
  console.error(e.message);   // "unknown service does-not-exist"
}

const result = await pm.callService("unstaked-api").catch((e) => {
  console.error("inactive:", e.message);  // "service X is not active"
  return null;
});
if (result && !result.success) {
  console.warn("called but no payment settled");
}
```

---

## Picking a backend

| You want to… | Use |
|--------------|-----|
| Run the demo offline / test agent logic | `LocalContractBackend` (Python default) |
| Talk to a running node (dashboard, demos) | `HttpContractBackend` (Python) / `HttpContractBackend` (JS) |
| Read/write the real deployed contracts | `CasperContractBackend` (Python) |

---

Next: [x402 Payments](x402-payments.md) · [API Reference](api-reference.md)
