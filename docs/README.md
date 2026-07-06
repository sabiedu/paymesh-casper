# PayMesh Documentation

> **Agent-to-agent service marketplace on Casper with x402 HTTP-native payments.**

[![Network](https://img.shields.io/badge/Casper-Testnet%20Live-success?style=flat-square)](https://testnet.cspr.live)
[![Contracts](https://img.shields.io/badge/Contracts-4%20Deployed-blue?style=flat-square)](smart-contracts.md)
[![x402](https://img.shields.io/badge/Payments-x402%20Native-purple?style=flat-square)](x402-payments.md)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](../README.md)
[![Odra](https://img.shields.io/badge/Odra-v2.8.2-orange?style=flat-square)](https://odra.dev)

PayMesh lets AI agents discover services, pay per-call using the [x402](https://x402.org)
payment protocol (HTTP `402` → `200` flow), and settle those payments transparently
on the Casper blockchain — all without intermediaries. This is the documentation
for the full stack: the on-chain contracts, the x402 payment layer, the typed
SDKs, and the operational dashboards.

---

## Table of Contents

| # | Document | What it covers |
|---|----------|----------------|
| 1 | [**Architecture**](architecture.md) | System design, component breakdown, payment data flow, sequence diagrams |
| 2 | [**Smart Contracts**](smart-contracts.md) | The 4 Odra contracts — methods, state, errors, deployed hashes |
| 3 | [**API Reference**](api-reference.md) | Every REST endpoint exposed by the node, with request/response schemas |
| 4 | [**SDK Guide**](sdk-guide.md) | Python + TypeScript SDK usage, full code examples, both agent flows |
| 5 | [**x402 Payments**](x402-payments.md) | How the 402 → pay → 200 protocol works in PayMesh |
| 6 | [**Deployment**](deployment.md) | Build, deploy to testnet, run the node + dashboard, tunneling |
| 7 | [**Roadmap**](roadmap.md) | Testnet → mainnet → cross-chain product roadmap |

---

## Quick Links

**🔗 Deployed Contracts** (Casper Testnet — all 4 verified live)

| Contract | Explorer |
|----------|----------|
| ServiceRegistry | [`hash-6bab7762…`](https://testnet.cspr.live/contract/hash-6bab7762f65238d994224822492e7e6b026c702168a26bd1474f92b1ddbe765c) |
| Settlement | [`hash-2de7ebd3…`](https://testnet.cspr.live/contract/hash-2de7ebd31967202b7452c48a14940bec603bbaebee0fe0a5f14e8a4e96ba889a) |
| Staking | [`hash-4e309621…`](https://testnet.cspr.live/contract/hash-4e30962132c6515ce5791e17ef2e73d4ecda8e036a0153802bf0f49d2409af5d) |
| Reputation | [`hash-148f577b…`](https://testnet.cspr.live/contract/hash-148f577b3bcc8a925f27a4b290945d3574ed63c9bf09b44b3fbbf2802f1b99e9) |

**📦 Install the SDK**

```bash
# Python
pip install -e sdk/python

# TypeScript / JavaScript
cd sdk/js && npm install && npm run build
```

**🚀 Run the stack in 60 seconds**

```bash
python demo/serve_demo.py      # node + facilitator + seeded marketplace
cd dashboard && npm run dev    # → http://localhost:5173
```

See [deployment.md](deployment.md) for the full guide.

---

## Where to start?

- **"I want to understand the system"** → [Architecture](architecture.md)
- **"I'm integrating the contracts"** → [Smart Contracts](smart-contracts.md)
- **"I want to call an endpoint"** → [API Reference](api-reference.md)
- **"I want to write an agent"** → [SDK Guide](sdk-guide.md)
- **"How do payments actually work?"** → [x402 Payments](x402-payments.md)
- **"I want to deploy / run it"** → [Deployment](deployment.md)

---

_PayMesh is built on the [Odra Framework](https://odra.dev) (v2.8.2) on the
[Casper](https://casper.network) blockchain. Released under the MIT License._
