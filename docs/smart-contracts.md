# Smart Contracts

PayMesh's on-chain core is **four independently deployable Odra contracts**,
written in Rust and compiled to WASM for the Casper blockchain.

```
src/
├── lib.rs                # crate root — re-exports the 4 modules
├── shared.rs             # ServiceInfo (shared record type)
├── service_registry.rs   # discovery layer
├── staking.rs            # provider collateral + slashing
├── settlement.rs         # on-chain payment attestation
└── reputation.rs         # aggregate ratings
```

> Built with the [Odra Framework](https://odra.dev) **v2.8.2**. Monetary amounts
> on Casper are in **motes** (1 CSPR = 1,000,000,000 motes).

---

## Deployed on Casper Testnet ✅

All four contracts are live on `casper-test` (protocol `2.2.2`).

| Contract | Package Hash | Deploy Hash | Explorer |
|----------|--------------|-------------|----------|
| **ServiceRegistry** | `hash-6bab7762f65238d994224822492e7e6b026c702168a26bd1474f92b1ddbe765c` | `01bef262` | [view ↗](https://testnet.cspr.live/contract/hash-6bab7762f65238d994224822492e7e6b026c702168a26bd1474f92b1ddbe765c) |
| **Settlement** | `hash-2de7ebd31967202b7452c48a14940bec603bbaebee0fe0a5f14e8a4e96ba889a` | `670733ef` | [view ↗](https://testnet.cspr.live/contract/hash-2de7ebd31967202b7452c48a14940bec603bbaebee0fe0a5f14e8a4e96ba889a) |
| **Staking** | `hash-4e30962132c6515ce5791e17ef2e73d4ecda8e036a0153802bf0f49d2409af5d` | `21fe2c77` | [view ↗](https://testnet.cspr.live/contract/hash-4e30962132c6515ce5791e17ef2e73d4ecda8e036a0153802bf0f49d2409af5d) |
| **Reputation** | `hash-148f577b3bcc8a925f27a4b290945d3574ed63c9bf09b44b3fbbf2802f1b99e9` | `4de3da53` | [view ↗](https://testnet.cspr.live/contract/hash-148f577b3bcc8a925f27a4b290945d3574ed63c9bf09b44b3fbbf2802f1b99e9) |

| | |
|---|---|
| **Deployer account** | `0203358a59f8208973c70520fbc0ac07776dd3e2b80c10c0c7c164b9122bbc25d9fc` |
| **Network** | `casper-test` |
| **Protocol version** | `2.2.2` |
| **Explorer** | [testnet.cspr.live](https://testnet.cspr.live) |
| **Compiler** | Odra v2.8.2 |

---

## Shared types (`shared.rs`)

The canonical service record, stored under its `service_id` in the registry.
The reputation and stake fields are a *denormalised snapshot* (authoritative
numbers live in the Reputation / Staking contracts) so the dashboard can render a
service in a single read.

```rust
pub struct ServiceInfo {
    pub service_id: String,        // provider-chosen opaque id (≤64 chars)
    pub provider: Address,         // owner / agent address
    pub name: String,              // human-readable name
    pub endpoint: String,          // base URL the resource server answers on
    pub price_per_call: U512,      // motes per successful call
    pub staking_amount: U512,      // minimum stake (motes) for "active"
    pub reputation_score: u32,     // basis points of a star (0–50000 ⇒ 0.00–5.00)
    pub total_ratings: u32,        // count behind reputation_score
    pub active: bool,              // listed & callable?
    pub registered_at: u64,        // block-time (seconds) at registration
}
```

---

## 1. ServiceRegistry (`service_registry.rs`)

The **discovery layer**. Provider agents publish what they offer; consumer agents
discover and inspect listings. Listings are keyed by `service_id` and additionally
indexed by provider address.

### State

| Variable | Type | Purpose |
|----------|------|---------|
| `services` | `Mapping<String, ServiceInfo>` | `service_id → full record` |
| `service_ids` | `List<String>` | every id, in insertion order (cheap listing) |
| `provider_services` | `Mapping<Address, Vec<String>>` | provider → their service ids |
| `owner` | `Var<Address>` | deployer / admin |
| `relayers` | `Mapping<Address, bool>` | addresses allowed to push reputation snapshots |

### Methods

| Method | Type | Description |
|--------|------|-------------|
| `init()` | constructor | records the deployer as owner |
| `transfer_owner(new_owner)` | write | owner-only |
| `add_relayer(relayer)` | write | whitelist a snapshot pusher (owner-only) |
| `revoke_relayer(relayer)` | write | owner-only |
| `register_service(id, name, endpoint, price_per_call, staking_amount)` | write | publish a new service (caller = provider) |
| `deregister_service(id)` | write | flip `active=false` (provider-only) |
| `reactivate_service(id)` | write | re-list a deregistered service (provider-only) |
| `update_reputation_snapshot(id, score, total_ratings)` | write | refresh denormalised score (owner/relayer-only) |
| `get_service(id)` | read | single service (reverts if absent) |
| `maybe_get_service(id)` | read | non-reverting lookup → `Option` |
| `list_services()` | read | all services, insertion order |
| `list_service_ids()` | read | just the ids (lighter) |
| `get_services_by_provider(addr)` | read | a provider's service ids |
| `service_count()` | read | number of registered services |
| `get_owner()` | read | current owner address |

### Events

`ServiceRegistered { service_id, provider, price_per_call }`
`ServiceDeregistered { service_id, provider }`
`ReputationSnapshotUpdated { service_id, reputation_score, total_ratings }`

### Errors (`RegistryError`)

| Code | Variant | Meaning |
|------|---------|---------|
| 1 | `ServiceAlreadyExists` | a service with that id is already registered |
| 2 | `ServiceNotFound` | no service with that id |
| 3 | `NotAuthorized` | caller is not the owner |
| 4 | `InvalidServiceId` | id empty or longer than 64 chars |
| 5 | `NotProvider` | caller is not the service's provider |

---

## 2. Staking (`staking.rs`)

Providers lock CSPR to back their services. A stake is **slashing collateral**:
governance can seize part of it for misbehaviour. Stakes are **time-locked** — a
provider requests withdrawal, waits the cooldown, then claims.

> `stake` is `#[odra(payable)]` — attach CSPR to the call. The default cooldown
> is **24 hours** (`DEFAULT_COOLDOWN_SECS = 86_400`).

### State

| Variable | Type | Purpose |
|----------|------|---------|
| `stakes` | `Mapping<String, StakeInfo>` | `service_id → stake record` |
| `cooldown_period` | `Var<u64>` | withdrawal cooldown (seconds) |
| `min_stake` | `Var<U512>` | minimum bonded stake (default 1 CSPR) |
| `owner` | `Var<Address>` | deployer / governance (slash authority) |
| `total_staked` | `Var<U512>` | running total of all live stakes |

```rust
pub struct StakeInfo {
    pub provider: Address,
    pub amount: U512,
    pub staked_at: u64,
    pub unlock_at: u64,           // 0 while locked; set when withdrawal requested
    pub slashed_total: U512,      // lifetime CSPR seized
}
```

### Methods

| Method | Type | Description |
|--------|------|-------------|
| `init()` | constructor | owner = caller; cooldown 24h; min stake 1 CSPR |
| `set_cooldown_period(secs)` | write | governance |
| `set_min_stake(amount)` | write | governance |
| `transfer_ownership(new_owner)` | write | governance |
| `stake(service_id)` | **payable write** | lock attached CSPR; top-ups re-lock |
| `request_withdraw(service_id)` | write | begin cooldown (provider-only) |
| `withdraw_stake(service_id)` | write | pay CSPR back after cooldown (provider-only) |
| `slash(service_id, amount, reason)` | write | governance-only; seize stake, reason recorded on-chain |
| `get_stake(service_id)` | read | stake record |
| `is_bonded(service_id)` | read | `true` if amount ≥ min_stake |
| `get_total_staked()` | read | aggregate CSPR locked |

### Events

`Staked { service_id, provider, amount, new_total }`
`WithdrawRequested { service_id, provider, unlock_at }`
`Withdrawn { service_id, provider, amount }`
`Slashed { service_id, provider, amount, reason }`

### Errors (`StakingError`)

| Code | Variant | Meaning |
|------|---------|---------|
| 1 | `NotAuthorized` | not the owner |
| 2 | `StakeNotFound` | no stake for that service |
| 3 | `WithdrawLocked` | still in cooldown / no pending request |
| 4 | `ZeroAmount` | staked 0 (or below min for a new position) |
| 5 | `InsufficientStake` | slash amount exceeds current stake |
| 6 | `NotProvider` | caller is not the original staker |

---

## 3. Settlement (`settlement.rs`)

Once an x402 payment is **verified**, it is recorded here so that every payment is
an immutable, queryable on-chain event, lifetime revenue is tallied per provider,
and the dashboard can stream a live feed.

> Only an authorised **recorder** (the PayMesh gateway / a facilitator) may call
> `record_payment`, because it attests the x402 proof was valid and the resource
> delivered. Actual CSPR movement happens off-chain via the facilitator.

### State

| Variable | Type | Purpose |
|----------|------|---------|
| `payments` | `List<PaymentRecord>` | append-only ledger |
| `service_payments` | `Mapping<String, Vec<u32>>` | service → payment indices |
| `provider_revenue` | `Mapping<Address, U512>` | provider → lifetime motes earned |
| `provider_payment_count` | `Mapping<Address, u32>` | provider → settled count |
| `owner` | `Var<Address>` | deployer / admin |
| `recorders` | `Mapping<Address, bool>` | authorised recorders |

```rust
pub struct PaymentRecord {
    pub index: u32,
    pub payer: Address,
    pub provider: Address,
    pub service_id: String,
    pub amount: U512,
    pub payment_proof: String,    // x402 payload / signature, base64
    pub timestamp: u64,           // block-time (seconds)
}
```

### Methods

| Method | Type | Description |
|--------|------|-------------|
| `init()` | constructor | owner = caller |
| `transfer_ownership(new_owner)` | write | owner-only |
| `add_recorder(recorder)` | write | authorise a gateway/facilitator |
| `revoke_recorder(recorder)` | write | owner-only |
| `record_payment(payer, provider, service_id, amount, payment_proof)` | write | recorder-only attestation |
| `get_revenue(provider)` | read | lifetime motes earned |
| `get_payment_count_for(provider)` | read | settled count |
| `get_payment_history(service_id)` | read | all payments for a service |
| `recent_payments(limit)` | read | most recent N (live feed) |

### Events

`PaymentSettled { payment_index, payer, provider, service_id, amount, payment_proof }`

### Errors (`SettlementError`)

| Code | Variant | Meaning |
|------|---------|---------|
| 1 | `NotAuthorized` | caller is not an authorised recorder |
| 2 | `ZeroAmount` | amount is zero |
| 3 | `InvalidServiceId` | service_id is empty |

---

## 4. Reputation (`reputation.rs`)

After a consumer receives a service over x402, it rates it. The contract keeps
every review and maintains a running aggregate so a browser can show a score
without scanning history. Each `(reviewer, service)` pair may rate **at most
once**; re-rating replaces the previous score.

### State

| Variable | Type | Purpose |
|----------|------|---------|
| `aggregates` | `Mapping<String, RatingAggregate>` | service → running aggregate |
| `reviews` | `List<Review>` | append-only review log |
| `service_reviews` | `Mapping<String, Vec<u32>>` | service → review indices |
| `rated` | `Mapping<(Address, String), u32>` | (reviewer, service) → review index |

```rust
pub struct RatingAggregate {
    pub total_score: u64,   // sum of current ratings
    pub count: u32,         // number behind total_score
    pub average: u32,       // basis points of a star (0–50000 ⇒ 0.00–5.00)
}

pub struct Review {
    pub index: u32,
    pub service_id: String,
    pub reviewer: Address,
    pub rating: u32,        // 1–5 inclusive
    pub review: String,     // ≤ 512 chars
    pub timestamp: u64,
}
```

### Methods

| Method | Type | Description |
|--------|------|-------------|
| `init()` | constructor | no-op (required by module system) |
| `update_reputation(service_id, rating, review)` | write | rate 1–5 (re-rate replaces) |
| `get_reputation(service_id)` | read | the running aggregate |
| `get_reviews(service_id)` | read | all reviews, oldest first |
| `total_reviews()` | read | count across the whole marketplace |

> The average is stored in **basis points of a star**: `average / 10_000 = rating`.
> e.g. `average = 45000` ⇒ 4.50 ★.

### Events

`ReputationUpdated { service_id, reviewer, rating, new_average }`

### Errors (`ReputationError`)

| Code | Variant | Meaning |
|------|---------|---------|
| 1 | `InvalidRating` | rating not in 1..=5 |
| 2 | `InvalidServiceId` | service_id is empty |
| 3 | `ReviewTooLong` | review text > `MAX_REVIEW_LEN` (512) |

---

## Interacting via Casper RPC

Contract reads/writes go through JSON-RPC. The SDK does this for you
(`CasperContractBackend` → `CasperRpcClient`), but you can also query directly:

```bash
# Put query to read ServiceInfo from the registry
curl -X POST https://rpc.testnet.casper.network/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "query_global_state",
    "params": {
      "state_identifier": { "BlockHeight": 0 },
      "key": "hash-6bab7762f65238d994224822492e7e6b026c702168a26bd1474f92b1ddbe765c",
      "path": []
    }
  }'
```

For programmatic access, use the Python SDK with the live backend:

```python
from paymesh import PayMeshClient, generate_account
from paymesh.backends import CasperContractBackend

pm = PayMeshClient(
    account=generate_account("observer"),
    backend=CasperContractBackend(
        rpc_url="https://rpc.testnet.casper.network/rpc",
        registry_hash="hash-6bab7762f65238d994224822492e7e6b026c702168a26bd1474f92b1ddbe765c",
    ),
)
for svc in pm.discover_services():
    print(svc.service_id, svc.price_per_call_cspr, svc.average_rating)
```

---

Next: [API Reference](api-reference.md) · [Deployment](deployment.md)
