# PayMesh Diagrams

Source diagrams for PayMesh docs. Mermaid blocks render natively on GitHub; the
ASCII diagrams are embedded directly in the relevant documents.

---

## 1. High-level architecture (ASCII)

Also at the top of [README.md](../README.md).

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

## 2. Four-layer stack (ASCII)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  DASHBOARD        React + Vite + Recharts + React Router                  │
│  / · /observe · /demo                                                    │
├──────────────────────────────────────────────────────────────────────────┤
│  SDK              PayMeshClient (Python + TypeScript)                     │
│  register · stake · call · rate · deposit · discover                     │
├──────────────────────────────────────────────────────────────────────────┤
│  x402 PAYMENT     Facilitator · x402 Client · Provider middleware         │
│  verify → settle → on-chain attestation · escrow ledger · replay defense  │
├──────────────────────────────────────────────────────────────────────────┤
│  SMART CONTRACTS  ServiceRegistry · Staking · Settlement · Reputation     │
│  Odra (Rust) → WASM → Casper testnet                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

## 3. Payment data flow (Mermaid)

Used in [architecture.md](../architecture.md).

```mermaid
sequenceDiagram
    autonumber
    participant C as Consumer Agent (SDK)
    participant P as Provider / Node
    participant F as Facilitator
    participant L as Settlement Ledger
    participant N as Casper (Settlement contract)

    C->>P: GET /serve/{service_id} (no payment)
    P-->>C: 402 Payment Required + PaymentRequirements
    Note over C: sign canonical auth with Ed25519 key
    C->>P: GET /serve/{service_id} + X-PAYMENT header
    P->>F: POST /settle (PaymentPayload, Requirements)
    F->>F: verify signature, recipient, amount, nonce
    F->>L: record_payment(payer, provider, amount)
    L-->>F: settlement tx / deploy hash
    F-->>P: SettleResponse { success, transaction }
    P-->>C: 200 OK + data + X-PAYMENT-RESPONSE
```

## 4. Roadmap progression (Mermaid)

Used in [roadmap.md](../roadmap.md).

```mermaid
graph LR
    A[Phase 1<br/>Testnet + SDKs] --> B[Phase 2<br/>Mainnet + packages]
    B --> C[Phase 3<br/>Cross-chain + DAO]
    C --> V((Vision:<br/>payment rails for<br/>M2M economy))
```
