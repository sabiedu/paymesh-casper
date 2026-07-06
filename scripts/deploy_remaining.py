"""Deploy remaining PayMesh contracts (Settlement, Reputation)."""
import sys, json, time
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

import requests
import pycspr
from pycspr import create_deploy_parameters, create_standard_payment, create_deploy, read_wasm
from pycspr.factory import create_private_key, create_public_key
from pycspr.crypto import get_key_pair_from_pem_file, KeyAlgorithm
from pycspr.types import ModuleBytes, DeployArgument, CL_String, CL_Bool

RPC_URL = "https://node.testnet.cspr.cloud/rpc"
AUTH_TOKEN = "55f79117-fc4d-4d60-9956-65423f39a06a"
CHAIN_NAME = "casper-test"
KEY_PEM = str(Path(__file__).parent.parent / "keys" / "deployer_secret_key.pem")
WASM_DIR = Path(__file__).parent.parent / "wasm"
GAS_PAYMENT = 800_000_000_000
HEADERS = {"Authorization": AUTH_TOKEN, "Content-Type": "application/json"}
CONTRACTS = ["Settlement", "Reputation"]

def rpc(method, params=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        payload["params"] = params
    return requests.post(RPC_URL, headers=HEADERS, json=payload, timeout=120).json()

def check_status(dhash, timeout=180):
    url = f"https://api.testnet.cspr.live/deploys/{dhash}"
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(url, headers={"Accept": "application/json"}, timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", {})
            if data.get("status") == "processed":
                err = data.get("error_message", "")
                cost = data.get("cost", "?")
                chash = data.get("contract_hash")
                if err:
                    print(f"  [FAIL] {err} (cost: {int(cost)/1e9:.1f} CSPR)")
                    return False
                else:
                    print(f"  [OK] Cost: {int(cost)/1e9:.1f} CSPR")
                    if chash:
                        print(f"       Contract: {chash}")
                    return True
        print(".", end="", flush=True)
        time.sleep(5)
    print(" [TIMEOUT]")
    return None

for name in CONTRACTS:
    print(f"\n{'='*50}")
    print(f"Deploying {name}...")
    print(f"{'='*50}")

    wasm_bytes = read_wasm(str(WASM_DIR / f"{name}.wasm"))

    # Fresh keys
    algo = KeyAlgorithm.SECP256K1
    pvk_bytes, pbk_bytes = get_key_pair_from_pem_file(KEY_PEM, algo)
    pvk = create_private_key(algo, pvk_bytes, pbk_bytes)
    pbk = create_public_key(algo, pbk_bytes)

    params = create_deploy_parameters(account=pbk, chain_name=CHAIN_NAME, ttl="30m", gas_price=1)
    payment = create_standard_payment(GAS_PAYMENT)
    session = ModuleBytes(
        args=[
            DeployArgument("odra_cfg_package_hash_key_name", CL_String(name.lower() + "_package_hash")),
            DeployArgument("odra_cfg_allow_key_override", CL_Bool(True)),
            DeployArgument("odra_cfg_is_upgradable", CL_Bool(True)),
            DeployArgument("odra_cfg_is_upgrade", CL_Bool(False)),
        ],
        module_bytes=wasm_bytes
    )

    deploy = create_deploy(params, payment, session)
    dhash = deploy.hash.hex()
    print(f"Hash: {dhash}")

    deploy.approve(pvk)

    # Serialize
    deploy_json = pycspr.to_json(deploy)
    if isinstance(deploy_json, str):
        deploy_json = json.loads(deploy_json)

    print(f"Submitting...")
    result = rpc("account_put_deploy", {"deploy": deploy_json})

    if "result" in result:
        submitted_hash = result["result"].get("deploy_hash", dhash)
        print(f"Submitted: {submitted_hash}")
        check_status(submitted_hash)
    elif "error" in result:
        err = result["error"]
        print(f"ERROR: {err.get('message')}")
        if "data" in err:
            print(f"  Detail: {str(err['data'])[:500]}")

    time.sleep(5)

print("\nDone!")
