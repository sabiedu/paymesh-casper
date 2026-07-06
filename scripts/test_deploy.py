"""
Test deploy a single Odra contract with higher gas.
"""
import sys
import json
import time
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
HEADERS = {"Authorization": AUTH_TOKEN, "Content-Type": "application/json"}

ALGO = KeyAlgorithm.SECP256K1
pvk_bytes, pbk_bytes = get_key_pair_from_pem_file(KEY_PEM, ALGO)
pvk = create_private_key(ALGO, pvk_bytes, pbk_bytes)
pbk = create_public_key(ALGO, pbk_bytes)
ACCOUNT_HEX = pycspr.crypto.get_account_key(ALGO, pbk_bytes).hex()

def rpc(method, params=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        payload["params"] = params
    return requests.post(RPC_URL, headers=HEADERS, json=payload, timeout=60).json()

def check_status(dhash, timeout=120):
    url = f"https://api.testnet.cspr.live/deploys/{dhash}"
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(url, headers={"Accept": "application/json"}, timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", {})
            if data.get("status") == "processed":
                return data
        print(".", end="", flush=True)
        time.sleep(5)
    return None

def try_deploy(name, wasm_path, gas_cspr):
    wasm_bytes = read_wasm(str(wasm_path))
    gas_motes = gas_cspr * 10**9

    print(f"\n[{name}] Deploying with {gas_cspr} CSPR gas...")

    params = create_deploy_parameters(account=pbk, chain_name=CHAIN_NAME, ttl="30m", gas_price=1)
    payment = create_standard_payment(gas_motes)
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
    deploy.approve(pvk)
    print(f"  Hash: {deploy.hash.hex()}")

    deploy_json = pycspr.to_json(deploy)
    if isinstance(deploy_json, str):
        deploy_json = json.loads(deploy_json)

    result = rpc("account_put_deploy", {"deploy": deploy_json})
    if "result" in result:
        dhash = result["result"].get("deploy_hash", deploy.hash.hex())
        print(f"  Submitted: {dhash}")
        data = check_status(dhash)
        if data:
            err = data.get("error_message", "")
            gas = data.get("consumed_gas", "?")
            cost = data.get("cost", "?")
            contract_hash = data.get("contract_hash")
            if err:
                print(f"  FAILED: {err} (gas: {gas}, cost: {cost})")
                return False
            else:
                print(f"  SUCCESS! Contract: {contract_hash}")
                print(f"  Gas: {gas} | Cost: {cost}")
                return True
        else:
            print("  TIMEOUT - check manually")
            return None
    elif "error" in result:
        print(f"  RPC ERROR: {result['error'].get('message')}")
        return False

# Try Reputation (smallest WASM) with escalating gas
wasm = Path(__file__).parent.parent / "wasm" / "Reputation.wasm"

for gas in [500, 1000]:
    ok = try_deploy("Reputation", wasm, gas)
    if ok:
        print("\n*** SUCCESS! This gas level works. ***")
        break
    elif ok is None:
        print("\n*** Timeout - deploy might still be processing ***")
        break
