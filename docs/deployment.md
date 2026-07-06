# Deployment

Everything you need to build the contracts, deploy them to Casper testnet, and run
the node + dashboard locally or on a public server.

---

## Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| Rust (stable) | latest | compile the Odra contracts |
| `cargo-odra` | matches Odra 2.8.2 | build + test + scaffold |
| Python | ≥ 3.10 | node, facilitator, SDK, demos |
| Node.js | ≥ 18 | build the dashboard |
| `pycspr` | latest | Casper testnet deploys |

```bash
# Rust + cargo-odra
rustup default stable
cargo install cargo-odra

# Python deps
pip install -r requirements.txt 2>/dev/null || pip install pycspr fastapi uvicorn requests pydantic cryptography
pip install -e sdk/python
```

---

## 1. Build the smart contracts

The four contracts are declared in `Odra.toml`:

```toml
[[contracts]]
fqn = "service_registry::ServiceRegistry"
[[contracts]]
fqn = "staking::Staking"
[[contracts]]
fqn = "settlement::Settlement"
[[contracts]]
fqn = "reputation::Reputation"
```

Build the WASM:

```bash
cargo odra build
```

This compiles each contract into `wasm/`:

```
wasm/
├── ServiceRegistry.wasm
├── Settlement.wasm
├── Staking.wasm
└── Reputation.wasm
```

Run the Rust integration tests on the OdraVM (no network needed):

```bash
cargo odra test
```

---

## 2. Deploy to Casper Testnet

Deployment uses the `pycspr`-based script at `scripts/deploy.py`, which submits
WASM module-byte deploys with the Odra-required args to the testnet RPC.

### 2a. Generate / load a deployer key

```bash
# Generate a fresh keypair (writes keys/secret_key.pem + keys/account_info.json)
python scripts/gen_keys.py
```

> The contracts were deployed with a **secp256k1** deployer key
> (`keys/deployer_secret_key.pem`). Fund the deployer account with testnet CSPR
> at the [testnet faucet](https://testnet.cspr.live/tools/faucet) — each contract
> deploy costs ~800 CSPR of gas (4 contracts ≈ 3,200 CSPR).

### 2b. Configure the livenet env (`.env`)

PayMesh/Odra reads testnet connection details from `.env`:

```bash
# .env — Casper Testnet Livenet Configuration (Odra 2.8.2)
ODRA_CASPER_LIVENET_NODE_ADDRESS=https://rpc.testnet.casper.network/rpc
ODRA_CASPER_LIVENET_EVENTS_URL=https://events.testnet.casper.network/events
ODRA_CASPER_LIVENET_CHAIN_NAME=casper-test
ODRA_CASPER_LIVENET_SECRET_KEY_PATH=./keys/secret_key.pem
ODRA_CASPER_LIVENET_TTL=900
ODRA_CASPER_LIVENET_GAS_PRICE_TOLERANCE=1
```

`scripts/deploy.py` itself also hardcodes the RPC endpoint, chain name, and gas
payment at the top of the file (`RPC_URL`, `CHAIN_NAME`, `GAS_PAYMENT`).

### 2c. Run the deployment

```bash
python scripts/deploy.py
```

The script, per contract: reads the WASM, builds Odra config args
(`odra_cfg_package_hash_key_name`, `odra_cfg_allow_key_override`,
`odra_cfg_is_upgradable`, `odra_cfg_is_upgrade`), signs a deploy with the
deployer key, submits it, waits for finalization, and records the package +
deploy hashes to `keys/deployment_results.json`.

### 2d. Current deployment (`keys/deployment_results.json`)

| Contract | Package Hash | Deploy Hash |
|----------|--------------|-------------|
| ServiceRegistry | `hash-6bab7762…765c` | `01bef2623188…377b9` |
| Settlement | `hash-2de7ebd3…889a` | `670733ef6068…4aa1` |
| Staking | `hash-4e309621…af5d` | `21fe2c7783b2…9373` |
| Reputation | `hash-148f577b…99e9` | `4de3da53d179…e4c1` |

- **Deployer account:** `0203358a59f8208973c70520fbc0ac07776dd3e2b80c10c0c7c164b9122bbc25d9fc`
- **Network:** `casper-test` (protocol `2.2.2`)
- **Deployment date:** `2026-07-06`

### 2e. Verify on-chain

```bash
# Check the deployer's balance / state
python scripts/check_balance.py

# Query the deployed contracts
python scripts/query_contracts.py
```

Full per-contract explorer links are in [smart-contracts.md](smart-contracts.md).

---

## 3. Run the node

The node (`x402/node.py`) is a single FastAPI process hosting the facilitator
(x402 verify/settle), the marketplace registry, the observability analytics, and
the demo console over one shared backend.

### All-in-one (recommended)

`demo/serve_demo.py` starts the node and seeds the marketplace with real data so
the dashboard is alive immediately:

```bash
python demo/serve_demo.py
# → node on :8001, seeded with 4 services + paid calls + ratings
```

It:
1. Boots the node (facilitator + registry + ledger) on port `8001`.
2. Reads the demo catalog (`GET /demo/catalog`).
3. Registers 4 services, each with 3–6 real paid x402 calls + ratings.
4. Stays up so the dashboard can poll it.

### Standalone (just the facilitator)

```bash
python -m x402.facilitator --port 8001
```

### Standalone node

```bash
python -m x402.node --port 8001
```

---

## 4. Run the dashboard

```bash
cd dashboard
npm install
npm run dev
# → http://localhost:5173
```

Three routes: `/` (marketplace), `/observe` (observability), `/demo` (console).

### Vite proxy configuration

The dev server proxies API calls to the node (`:8001`) so everything is
same-origin — no CORS, one hostname. From `dashboard/vite.config.ts`:

```ts
server: {
  port: 5173,
  host: true,                       // bind all interfaces
  proxy: {
    "/registry":         { target: "http://127.0.0.1:8001", changeOrigin: true },
    "/agent":            { target: "http://127.0.0.1:8001", changeOrigin: true },
    "/recent_payments":  { target: "http://127.0.0.1:8001", changeOrigin: true },
    "/serve":            { target: "http://127.0.0.1:8001", changeOrigin: true },
    "/health":           { target: "http://127.0.0.1:8001", changeOrigin: true },
    "/demo":    { target: "http://127.0.0.1:8001", changeOrigin: true,
                  // SPA page route stays client-side; only API sub-paths proxy
                  bypass: (req) => { if (req.method==="GET" && /^\/demo\/?(\?.*)?$/.test(req.url)) return "/index.html"; } },
    "/observe": { target: "http://127.0.0.1:8001", changeOrigin: true,
                  bypass: (req) => { if (req.method==="GET" && /^\/observe\/?(\?.*)?$/.test(req.url)) return "/index.html"; } },
  },
}
```

The `bypass` functions return `index.html` for the bare `/demo` and `/observe`
*page* routes so React Router handles them, while still proxying API sub-paths
(`/demo/activity`, `/observe/metrics`, …).

---

## 5. Run the demo agents (CLI)

For a terminal-driven demo instead of the UI:

```bash
# Start node + provider (all-in-one)
python demo/serve_demo.py

# In another shell, run the consumer agent
python demo/consumer_agent.py --node http://127.0.0.1:8001 --calls 5

# Or the full scripted demo
python demo/run_demo.py
```

`consumer_agent.py` flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--node` | `http://127.0.0.1:8001` | node URL |
| `--key` | *(generated)* | Ed25519 private key hex (else fresh identity) |
| `--fund` | `10.0` | CSPR to fund escrow |
| `--calls` | `3` | paid calls to make |
| `--service` | `risk-score-api` | target service |

---

## 6. Testing

```bash
# Rust integration tests (OdraVM)
cargo odra test

# Python SDK tests
pytest sdk/python/tests/

# Build the JS SDK
cd sdk/js && npm run build
```

---

## Port reference

| Port | Service |
|------|---------|
| `8001` | PayMesh node (facilitator + registry + demo + observe) |
| `8002` | standalone x402 provider (when run separately) |
| `5173` | Vite dashboard dev server |

---

Next: [Roadmap](roadmap.md) · [API Reference](api-reference.md)
