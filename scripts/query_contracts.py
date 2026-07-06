"""Query contract hashes using pycspr's account hash."""
import requests
import pycspr
from pycspr.crypto import get_key_pair_from_pem_file, KeyAlgorithm
from pathlib import Path

KEY_PEM = str(Path(__file__).parent.parent / "keys" / "deployer_secret_key.pem")
AUTH = '55f79117-fc4d-4d60-9956-65423f39a06a'
HEADERS = {'Authorization': AUTH, 'Content-Type': 'application/json'}

algo = KeyAlgorithm.SECP256K1
pvk_bytes, pbk_bytes = get_key_pair_from_pem_file(KEY_PEM, algo)

# Get the account hash using pycspr
account_hash = pycspr.crypto.get_account_key(algo, pbk_bytes)
ah_hex = pycspr.crypto.get_account_hash(account_hash).hex()
print(f"Account hash: {ah_hex}")
print(f"Account hash prefixed: account-hash-{ah_hex}")

# Get state root hash
r = requests.post('https://node.testnet.cspr.cloud/rpc', headers=HEADERS,
    json={'jsonrpc': '2.0', 'id': 1, 'method': 'chain_get_state_root_hash', 'params': {}},
    timeout=15)
srh = r.json().get('result', {}).get('state_root_hash', '')
print(f"State root hash: {srh}")

# query_global_state with correct account-hash format
r = requests.post('https://node.testnet.cspr.cloud/rpc', headers=HEADERS,
    json={
        'jsonrpc': '2.0', 'id': 1,
        'method': 'query_global_state',
        'params': {
            'key': f'account-hash-{ah_hex}',
            'path': []
        }
    },
    timeout=30)

d = r.json()
if 'result' not in d:
    # Try with state_root_hash as state_identifier
    r = requests.post('https://node.testnet.cspr.cloud/rpc', headers=HEADERS,
        json={
            'jsonrpc': '2.0', 'id': 1,
            'method': 'query_global_state',
            'params': {
                'state_identifier': {'Type': 'StateRootHash', 'Hash': srh},
                'key': f'account-hash-{ah_hex}',
                'path': []
            }
        },
        timeout=30)
    d = r.json()

if 'result' in d:
    sv = d['result'].get('stored_value', {})
    if 'Account' in sv:
        nks = sv['Account'].get('named_keys', [])
        print(f"\nNamed keys ({len(nks)}):")
        for nk in nks:
            print(f"  {nk.get('name')}: {nk.get('key')}")
    else:
        print(f"Stored value: {list(sv.keys())}")
else:
    err = d.get('error', {})
    print(f"\nError: {err.get('message', d)}")
    print(f"  Detail: {err.get('data', '')[:300]}")
