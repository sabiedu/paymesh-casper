"""Generate Ed25519 keypair for Casper Testnet deployment."""
import json
import secrets
from pathlib import Path

import pycspr
from pycspr.crypto import KeyAlgorithm, get_key_pair_from_bytes, get_account_key, get_account_hash

KEYS_DIR = Path(__file__).parent.parent / "keys"
KEYS_DIR.mkdir(exist_ok=True)

algo = KeyAlgorithm.ED25519

# Generate a random 32-byte seed (Ed25519 private key)
seed = secrets.token_bytes(32)

# Derive key pair from seed
pvk, pbk = get_key_pair_from_bytes(seed, algo)

# Save PEM files
pvk_pem = pycspr.crypto.get_pvk_pem_from_bytes(pvk, algo)
if isinstance(pvk_pem, bytes):
    pvk_pem = pvk_pem.decode("utf-8")
(KEYS_DIR / "secret_key.pem").write_text(pvk_pem, encoding="utf-8")

# Get account info
account_key = get_account_key(algo, pbk)
account_key_hex = account_key.hex()
account_hash = get_account_hash(account_key)
account_hash_hex = account_hash.hex() if isinstance(account_hash, bytes) else bytes(account_hash).hex()

# Public key hex (with algorithm prefix)
pub_hex = pbk.hex()

print(f"Algorithm:         Ed25519")
print(f"Private Key (hex): {pvk.hex()}")
print(f"Public Key (hex):  02{pub_hex}")
print(f"Account Key:       {account_key_hex}")
print(f"Account Hash:      {account_hash_hex}")
print(f"Keys saved to:     {KEYS_DIR}")

# Save account info
info = {
    "algorithm": "ed25519",
    "account_hash": account_hash_hex,
    "account_key": account_key_hex,
    "public_key_hex": f"02{pub_hex}",
    "private_key_hex": pvk.hex(),
}
(KEYS_DIR / "account_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
print(f"\n✅ Account info saved to {KEYS_DIR / 'account_info.json'}")
