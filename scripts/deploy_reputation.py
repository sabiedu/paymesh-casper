"""Deploy Reputation contract standalone."""
import sys, json, time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import requests
import pycspr
from pycspr import create_deploy_parameters, create_standard_payment, create_deploy, read_wasm
from pycspr.factory import create_private_key, create_public_key
from pycspr.crypto import get_key_pair_from_pem_file, KeyAlgorithm
from pycspr.types import ModuleBytes, DeployArgument, CL_String, CL_Bool

RPC_URL = "https://node.testnet.cspr.cloud/rpc"
AUTH_TOKEN = "55f79117-fc4d-4d60-9956-65423f39a06a"
HEADERS = {"Authorization": AUTH_TOKEN, "Content-Type": "application/json"}

print("Deploying Reputation...")

wasm_bytes = read_wasm(str(Path(__file__).parent.parent / "wasm" / "Reputation.wasm"))

algo = KeyAlgorithm.SECP256K1
pvk_bytes, pbk_bytes = get_key_pair_from_pem_file(str(Path(__file__).parent.parent / "keys" / "deployer_secret_key.pem"), algo)
pvk = create_private_key(algo, pvk_bytes, pbk_bytes)
pbk = create_public_key(algo, pbk_bytes)

params = create_deploy_parameters(account=pbk, chain_name="casper-test", ttl="30m", gas_price=1)
payment = create_standard_payment(800_000_000_000)
session = ModuleBytes(
    args=[
        DeployArgument("odra_cfg_package_hash_key_name", CL_String("reputation_package_hash")),
        DeployArgument("odra_cfg_allow_key_override", CL_Bool(True)),
        DeployArgument("odra_cfg_is_upgradable", CL_Bool(True)),
        DeployArgument("odra_cfg_is_upgrade", CL_Bool(False)),
    ],
    module_bytes=wasm_bytes
)

deploy = create_deploy(params, payment, session)
print(f"Hash: {deploy.hash.hex()}")
deploy.approve(pvk)

deploy_json = pycspr.to_json(deploy)
if isinstance(deploy_json, str):
    deploy_json = json.loads(deploy_json)

result = requests.post(RPC_URL, headers=HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "account_put_deploy", "params": {"deploy": deploy_json}}, timeout=120).json()

if "result" in result:
    dhash = result["result"].get("deploy_hash", deploy.hash.hex())
    print(f"Submitted: {dhash}")
    # Wait for confirmation
    for _ in range(36):
        time.sleep(5)
        r = requests.get(f"https://api.testnet.cspr.live/deploys/{dhash}", headers={"Accept": "application/json"}, timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", {})
            if data.get("status") == "processed":
                err = data.get("error_message", "")
                cost = int(data.get("cost", 0)) / 1e9
                chash = data.get("contract_hash")
                if err:
                    print(f"FAILED: {err} (cost: {cost:.1f} CSPR)")
                else:
                    print(f"SUCCESS! Cost: {cost:.1f} CSPR")
                    if chash:
                        print(f"Contract hash: {chash}")
                break
        print(".", end="", flush=True)
    else:
        print(" TIMEOUT")
elif "error" in result:
    print(f"ERROR: {result['error'].get('message')}")
    if "data" in result["error"]:
        print(f"  Detail: {str(result['error']['data'])[:500]}")
