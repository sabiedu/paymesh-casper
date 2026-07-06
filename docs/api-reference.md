# API Reference

Every REST endpoint exposed by the **PayMesh node** — a single FastAPI process
that composes the x402 facilitator, the marketplace registry, the demo console,
and the observability analytics over one shared backend.

> The node is created by `x402/node.py:create_paymesh_node_app()` and mounts the
> facilitator (`x402/facilitator.py`), the observability endpoints
> (`x402/observe_endpoints.py`), and the demo endpoints
> (`x402/demo_endpoints.py`). Default base URL: `http://127.0.0.1:8001`.

**Conventions**

- Monetary amounts in request/response bodies are in **CSPR** (floats) unless a
  field is suffixed `_motes` (integers; 1 CSPR = 10⁹ motes).
- All `POST` bodies are `application/json`.
- The node enables permissive CORS so the Vite dashboard can call it same-origin.

---

## Endpoint Index

| # | Group | Method | Path |
|---|-------|--------|------|
| 1 | [Registry](#registry) | POST | `/registry/services` |
| 2 | | POST | `/registry/services/{service_id}/stake` |
| 3 | | GET | `/registry/services` |
| 4 | | GET | `/registry/services/{service_id}` |
| 5 | | POST | `/registry/services/{service_id}/rate` |
| 6 | | GET | `/registry/services/{service_id}/reputation` |
| 7 | | GET | `/registry/services/{service_id}/reviews` |
| 8 | | GET | `/registry/stats` |
| 9 | | POST | `/registry/deposit` |
| 10 | [Payments](#payments--facilitator) | POST | `/verify` |
| 11 | | POST | `/settle` |
| 12 | | GET | `/balances/{account}` |
| 13 | | GET | `/recent_payments` |
| 14 | [Agent](#agent) | POST | `/agent/call` |
| 15 | [Demo](#demo-console) | POST | `/demo/register-provider` |
| 16 | | POST | `/demo/consumer-call` |
| 17 | | POST | `/demo/run-full-flow` |
| 18 | | GET | `/demo/activity` |
| 19 | | GET | `/demo/catalog` |
| 20 | | GET/POST | `/serve/{service_id}` |
| 21 | [Observability](#observability) | GET | `/observe/metrics` |
| 22 | [Health](#health) | GET | `/health` |

---

## Registry

### `POST /registry/services`

Register a new marketplace service.

**Request body** — `RegisterReq`

```json
{
  "provider": "01a1b2c3...d4e5f6",
  "service_id": "risk-score-api",
  "name": "Risk Score API",
  "endpoint": "http://127.0.0.1:8002/risk",
  "price_per_call_cspr": 0.05,
  "staking_amount_cspr": 5.0
}
```

**Response** — the created `ServiceInfo` (see shape below).

```bash
curl -X POST http://127.0.0.1:8001/registry/services \
  -H "Content-Type: application/json" \
  -d '{"provider":"01a1b2c3","service_id":"risk-score-api","name":"Risk Score API","endpoint":"http://127.0.0.1:8002/risk","price_per_call_cspr":0.05,"staking_amount_cspr":5.0}'
```

> **`ServiceInfo` shape** (returned by most registry endpoints):

```json
{
  "service_id": "risk-score-api",
  "provider": "01a1b2c3...d4e5f6",
  "name": "Risk Score API",
  "endpoint": "http://127.0.0.1:8002/risk",
  "price_per_call_motes": 50000000,
  "price_per_call_cspr": 0.05,
  "staking_amount_motes": 5000000000,
  "staking_amount_cspr": 5.0,
  "reputation_score": 45000,
  "average_rating": 4.5,
  "total_ratings": 12,
  "active": true,
  "registered_at": 1751788800
}
```

### `POST /registry/services/{service_id}/stake`

Lock CSPR behind a service (activates it once the minimum is met).

**Request body** — `StakeReq`

```json
{ "provider": "01a1b2c3...d4e5f6", "amount_cspr": 5.0 }
```

**Response** — the updated `ServiceInfo`.

```bash
curl -X POST http://127.0.0.1:8001/registry/services/risk-score-api/stake \
  -H "Content-Type: application/json" \
  -d '{"provider":"01a1b2c3","amount_cspr":5.0}'
```

### `GET /registry/services`

Discover marketplace services.

**Query params**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `active_only` | bool | `true` | only active services |
| `category` | string | — | case-insensitive name substring filter |

**Response**

```json
{ "services": [ { /* ServiceInfo */ }, ... ] }
```

```bash
curl "http://127.0.0.1:8001/registry/services?active_only=true&category=oracle"
```

### `GET /registry/services/{service_id}`

Read a single service. **404** if not found.

```bash
curl http://127.0.0.1:8001/registry/services/risk-score-api
```

### `POST /registry/services/{service_id}/rate`

Rate a service 1–5 with an optional review.

**Request body** — `RateReq`

```json
{ "reviewer": "01b2c3d4...e5f6a7", "rating": 5, "review": "fast & accurate" }
```

**Response**

```json
{ "count": 13, "average_rating": 4.62 }
```

```bash
curl -X POST http://127.0.0.1:8001/registry/services/risk-score-api/rate \
  -H "Content-Type: application/json" \
  -d '{"reviewer":"01b2c3d4","rating":5,"review":"fast & accurate"}'
```

### `GET /registry/services/{service_id}/reputation`

```json
{ "count": 13, "average_rating": 4.62, "reputation_score": 46200 }
```

### `GET /registry/services/{service_id}/reviews`

```json
{
  "reviews": [
    { "index": 0, "service_id": "risk-score-api", "reviewer": "01b2c3d4",
      "rating": 5, "review": "fast & accurate", "timestamp": 1751788860 }
  ]
}
```

### `GET /registry/stats`

Marketplace-wide stats for the dashboard.

```json
{
  "service_count": 5,
  "active_services": 4,
  "total_staked_cspr": 25.0,
  "total_payments": 42,
  "total_volume_cspr": 2.1,
  "services": [ { /* ServiceInfo */ }, ... ]
}
```

### `POST /registry/deposit`

Credit an escrow balance (funds a consumer so the facilitator can settle
per-call payments).

**Request body** — `DepositReq`

```json
{ "account": "01b2c3d4...e5f6a7", "amount_cspr": 10.0 }
```

**Response**

```json
{ "ok": true, "balance_cspr": 10.0 }
```

---

## Payments / Facilitator

The x402 facilitator verifies payment signatures and records settlements.

### `POST /verify`

Validate a `PaymentPayload` **without** settling.

**Request body** — `VerifyRequest`

```json
{
  "paymentPayload": {
    "x402_version": 1,
    "scheme": "casper-exact",
    "network": "casper-testnet",
    "payload": {
      "from": "01a1b2c3...",
      "to": "01d4e5f6...",
      "value": "50000000",
      "service_id": "risk-score-api",
      "nonce": "9f2c1a8b...",
      "authorization": "01a1b2c3...\n01d4e5f6...\n50000000\nrisk-score-api\n9f2c1a8b..."
    },
    "signature": "8e3b..."
  },
  "paymentRequirements": {
    "scheme": "casper-exact",
    "network": "casper-testnet",
    "maxAmountRequired": "50000000",
    "pay_to": "01d4e5f6...",
    "resource": "http://127.0.0.1:8002/risk",
    "asset": "CSPR",
    "expires": 0
  }
}
```

**Response** — `VerifyResponse`

```json
{ "isValid": true, "isVerified": true }
```

On failure: `{ "isValid": false, "isVerified": false, "error": "invalid signature" }`.

### `POST /settle`

Verify **and** settle; returns a settlement receipt. Records the payment on the
ledger (and, in testnet mode, as an on-chain attestation). Single-use nonces
guard against replay.

**Request body** — same as `/verify` (`SettleRequest`).

**Response** — `SettleResponse`

```json
{
  "success": true,
  "network": "casper-testnet",
  "transaction": "tx-000123",
  "payer": "01a1b2c3...",
  "payee": "01d4e5f6..."
}
```

On failure: `{ "success": false, "payer": "...", "error": "nonce already used (replay)" }`.

### `GET /balances/{account}`

Read an escrow balance.

```bash
curl http://127.0.0.1:8001/balances/01b2c3d4
# { "account": "01b2c3d4", "balance_motes": 10000000000 }
```

### `GET /recent_payments`

Read the payment feed (dashboard live feed).

| Param | Type | Default |
|-------|------|---------|
| `limit` | int | `20` |

```json
{
  "payments": [
    {
      "index": 41,
      "payer": "01a1b2c3...",
      "provider": "01d4e5f6...",
      "service_id": "risk-score-api",
      "amount_motes": 50000000,
      "payment_proof": "8e3b...",
      "timestamp": 1751788860
    }
  ]
}
```

---

## Agent

### `POST /agent/call`

Run the full x402 consumer flow server-side and return the result — the same flow
`demo/consumer_agent.py` performs, triggered with one click. Generates a fresh
consumer identity, funds 10 CSPR of escrow, and calls the service via x402.

**Request body** — `AgentCallReq`

```json
{ "service_id": "risk-score-api", "wallet": "0xabc123..." }
```

(`wallet` is optional and passed as a query param to the paid route.)

**Response** (success)

```json
{
  "success": true,
  "data": { "score": 0.87, "label": "low", ... },
  "amount_paid_cspr": 0.05,
  "settlement_id": "tx-000123",
  "consumer": "01c3d4e5...",
  "service_id": "risk-score-api"
}
```

**Response** (provider not serving a paid route)

```json
{
  "success": false,
  "data": null,
  "amount_paid_cspr": 0.0,
  "settlement_id": "",
  "consumer": "01c3d4e5...",
  "service_id": "risk-score-api",
  "error": "This service is listed on the marketplace but its provider endpoint isn't serving a paid route yet…"
}
```

---

## Demo Console

The interactive demo engine — exercises the real SDK code paths from buttons.

### `POST /demo/register-provider`

Generate a provider identity, register + stake a service from the catalog, and
mount a callable x402 paid route.

**Request body**

```json
{ "service_id": "sentiment-analysis-api" }
```

**Response** — the created service + activity event, e.g.

```json
{ "service": { /* ServiceInfo */ }, "run_id": "run-3" }
```

### `POST /demo/consumer-call`

Generate/fund a consumer and make **one** real x402 paid call.

**Request body** — `ConsumerCallReq`

```json
{ "service_id": "sentiment-analysis-api", "wallet": "0xabc..." }
```

### `POST /demo/run-full-flow`

The one-click "wow": register → stake → 3–4 paid calls → rate, in one call.

### `GET /demo/activity`

Recent activity events (the live console log). Color-coded by `type`:
`provider | consumer | payment | settlement | rating | discover | system`.

| Param | Type | Default |
|-------|------|---------|
| `since_id` | int | `0` |
| `limit` | int | `200` |

```json
{
  "events": [
    { "id": 1, "ts": 1751788800.0, "type": "provider",
      "icon": "🟣", "message": "Registered sentiment-analysis-api", "run_id": "run-1" }
  ]
}
```

### `GET /demo/catalog`

The preset service catalog the demo picks from.

```json
{
  "services": [
    { "service_id": "sentiment-analysis-api", "name": "AI Sentiment Analysis",
      "emoji": "💬", "tag": "AI Model", "price_cspr": 0.05 },
    { "service_id": "price-oracle-api", "name": "On-Chain Price Oracle",
      "emoji": "📈", "tag": "Oracle", "price_cspr": 0.05 },
    { "service_id": "wallet-screening-api", "name": "Wallet Risk Screening",
      "emoji": "🛡️", "tag": "Risk Engine", "price_cspr": 0.05 },
    { "service_id": "defi-yield-api", "name": "DeFi Yield Optimizer",
      "emoji": "🌾", "tag": "DeFi", "price_cspr": 0.08 },
    { "service_id": "nft-valuation-api", "name": "NFT Valuation Engine",
      "emoji": "🖼️", "tag": "Valuation", "price_cspr": 0.06 }
  ]
}
```

### `GET | POST /serve/{service_id}`

The x402 paid route that serves each demo service's payload. Without payment it
responds `402` with `PaymentRequirements`; with a valid `X-PAYMENT` header it
settles and returns `200` + the service-specific payload (sentiment score, price,
risk score, yield/APY, NFT valuation…).

---

## Observability

### `GET /observe/metrics`

Aggregated analytics for the `/observe` dashboard, computed entirely from real
in-memory marketplace state — no faked numbers.

```json
{
  "summary": {
    "total_volume_cspr": 2.1,
    "total_payments": 42,
    "total_services": 5,
    "active_services": 4,
    "total_staked_cspr": 25.0,
    "avg_reputation": 4.5,
    "total_agents": 9,
    "uptime_seconds": 1832
  },
  "volume_timeseries": [
    { "t": 1751788800, "label": "12:00:00", "volume_cspr": 0.0 },
    { "t": 1751789800, "label": "12:16:40", "volume_cspr": 0.15 }
  ],
  "payments_per_service": [
    { "service_id": "risk-score-api", "name": "Risk Score API",
      "call_count": 12, "volume_cspr": 0.6 }
  ],
  "reputation_breakdown": [
    { "service_id": "risk-score-api", "name": "Risk Score API",
      "rating": 4.5, "ratings_count": 12 }
  ],
  "contracts": [
    { "name": "ServiceRegistry", "package_hash": "hash-6bab7762…",
      "deploy_hash": "01bef262", "status": "active" }
  ],
  "agent_registry": [
    { "address": "01a1b2c3…", "role": "provider",
      "services_offered": 2, "stake_cspr": 10.0,
      "paid_cspr": 0.0, "reputation": 0.0, "last_active": 1751789800 }
  ],
  "network": {
    "network": "Casper Testnet",
    "chain_name": "casper-test",
    "protocol": "2.2.2",
    "rpc_status": "connected",
    "explorer_url": "https://testnet.cspr.live",
    "current_node": "http://127.0.0.1:8001",
    "generated_at": 1751789800
  }
}
```

---

## Health

### `GET /health`

Liveness probe used by the Vite proxy and any load balancer / tunnel.

```json
{ "status": "ok" }
```

---

Next: [SDK Guide](sdk-guide.md) · [x402 Payments](x402-payments.md)
