# PayMesh Python SDK

Typed client for the **x402 agent marketplace on Casper**.

```python
from paymesh import PayMeshClient, generate_account

acct = generate_account("alice")
pm = PayMeshClient(account=acct, facilitator_url="http://127.0.0.1:8001")
pm.deposit(10.0)

pm.register_service("risk-api", "Risk API", "http://127.0.0.1:8002/risk", 0.05, 5.0)
pm.stake("risk-api", 5.0)

result = pm.call_service("risk-api")          # pays per-call via x402
pm.rate_service("risk-api", 5, "fast")
```

`call_service` automatically performs the full x402 handshake: it receives the
`402 Payment Required` challenge, signs a payment with the account's Casper
Ed25519 key, settles via the facilitator, and retries — returning the resource
plus a settlement receipt recorded on the Settlement layer.

See the [project root README](../../README.md) for the full architecture.
