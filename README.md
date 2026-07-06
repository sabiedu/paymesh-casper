# PayMesh

**Agent-to-agent service marketplace on Casper with x402 HTTP-native payments.**

PayMesh lets AI agents discover services, pay per-call using the [x402](https://x402.org) payment protocol (HTTP 402 → 200 flow), and settle those payments transparently on the Casper blockchain — all without intermediaries.

```
┌──────────┐   x402 payment    ┌──────────────┐   on-chain settle   ┌─────────────────┐
│  Consumer │ ───────────────→ │  Facilitator  │ ─────────────────→ │  Casper Testnet  │
│   Agent   │ ← 200 OK + data  │  (FastAPI)    │ ←  receipt         │  4 Odra contracts│
└──────────┘                   └──────────────┘                     └─────────────────┘
                                        ↕                                    ↕
                                ┌──────────────┐                     ┌─────────────────┐
                                │   Provider   │ ← service call      │  PayMesh Python  │
                                │    Agent     │ ──────────────→     │       SDK        │
                                └──────────────┘                     └─────────────────┘
```

## Smart Contracts (Odra / Rust)

Four independently deployable contracts form the on-chain backbone:

| Contract | Responsibility |
|----------|---------------|
| **ServiceRegistry** | Agents register services (name, endpoint, price-per-call, stake). Discoverable via on-chain queries. |
| **Staking** | Providers lock CSPR collateral to list services. Slashing mechanism for misbehaviour. |
| **Settlement** | Verified x402 payments are recorded on-chain. Revenue tallied per provider. Escrow deposits & withdrawals. |
| **Reputation** | Consumers rate services (1–5 stars). Contract maintains aggregate score and review count. |

### Deployed on Casper Testnet ✅

| Contract | Package Hash |
|----------|-------------|
| ServiceRegistry | `hash-6bab7762f65238d994224822492e7e6b026c702168a26bd1474f92b1ddbe765c` |
| Settlement | `hash-2de7ebd31967202b7452c48a14940bec603bbaebee0fe0a5f14e8a4e96ba889a` |
| Staking | `hash-4e30962132c6515ce5791e17ef2e73d4ecda8e036a0153802bf0f49d2409af5d` |
| Reputation | `hash-148f577b3bcc8a925f27a4b290945d3574ed63c9bf09b44b3fbbf2802f1b99e9` |

**Deployer:** `0203358a59f8208973c70520fbc0ac07776dd3e2b80c10c0c7c164b9122bbc25d9fc`
**Network:** `casper-test` (protocol 2.2.2)
**Explorer:** [testnet.cspr.live](https://testnet.cspr.live)

## x402 Payment Layer

The x402 protocol enables HTTP-native micropayments:

1. **Consumer agent** requests a paid API endpoint
2. **Provider** responds with `402 Payment Required` + `PaymentRequirements`
3. **Consumer** signs a payment payload with their Casper key
4. **Facilitator** verifies the signature and settles on-chain
5. **Provider** serves the data (HTTP `200 OK`)

```python
from x402.client import x402Client
from x402.crypto import generate_account

account = generate_account("alice")
client = x402Client(account=account, facilitator_url="http://127.0.0.1:8001")

# Automatically handles the 402 → payment → 200 flow
response = client.get("http://127.0.0.1:8002/risk?portfolio=tech")
```

### Facilitator API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/verify` | POST | Validate a `PaymentPayload` without settling |
| `/settle` | POST | Verify and settle; returns settlement receipt |
| `/balances/{account}` | GET | Read escrow balance |
| `/recent_payments` | GET | Read payment feed |

## Python SDK

```bash
pip install -e sdk/python
```

```python
from paymesh import PayMeshClient, generate_account

account = generate_account("alice")
pm = PayMeshClient(account=account, facilitator_url="http://127.0.0.1:8001")

# Fund escrow
pm.deposit(10.0)

# Provider: register & stake
pm.register_service("risk-api", "Risk API", "http://localhost:8002/risk", 0.05, 5.0)
pm.stake("risk-api", 5.0)

# Consumer: discover, call, rate
services = pm.discover_services()
result = pm.call_service("risk-api")    # pays via x402 automatically
pm.rate_service("risk-api", 5, "fast & accurate")

print(pm.get_reputation("risk-api"))     # aggregate score
```

## Architecture

```
paymesh-casper/
├── src/                    # Odra smart contracts (Rust)
│   ├── service_registry.rs
│   ├── staking.rs
│   ├── settlement.rs
│   ├── reputation.rs
│   └── shared.rs           # shared types & errors
├── wasm/                   # Compiled WASM (deployed to Testnet)
├── x402/                   # x402 payment protocol implementation
│   ├── facilitator.py      # FastAPI payment facilitator
│   ├── client.py           # x402 HTTP client
│   ├── crypto.py           # Payment signature verification
│   ├── ledger.py           # On-chain settlement ledger
│   └── encoding.py         # x402 standard encoding
├── sdk/python/paymesh/     # Python SDK
│   ├── client.py           # PayMeshClient (typed entry point)
│   ├── backends.py         # Local + Casper contract backends
│   ├── casper_client.py    # Direct Casper RPC client
│   └── models.py           # Data models
├── demo/                   # Live demo (consumer + provider agents)
├── scripts/                # Deployment & utility scripts
└── tests/                  # Integration tests
```

## Quick Start

### 1. Start the facilitator
```bash
python -m x402.facilitator --port 8001
```

### 2. Start a provider agent
```bash
python demo/provider_agent.py
```

### 3. Run the consumer
```bash
python demo/consumer_agent.py
```

## Contract Build

```bash
# Build WASM (requires cargo-odra)
cargo odra build
```

Built with [Odra Framework](https://odra.dev) v2.8.2 on Casper blockchain.

## Testing

```bash
# Rust integration tests (OdraVM)
cargo odra test

# Python SDK tests
pytest sdk/python/tests/
```

## Tech Stack

- **Blockchain:** Casper (Odra smart contracts in Rust)
- **Payments:** x402 HTTP-native payment protocol
- **Backend:** FastAPI (facilitator)
- **SDK:** Python (type-safe, async-ready)
- **Crypto:** secp256k1 signatures (Casper-compatible)

## License

MIT
