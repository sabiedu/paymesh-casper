"""Check account balance - raw debug output."""
import requests
import sys
sys.stdout.reconfigure(encoding="utf-8")

PUBLIC_KEY = "0203358a59f8208973c70520fbc0ac07776dd3e2b80c10c0c7c164b9122bbc25d9fc"

# Try CSPR.live REST API
url = f"https://api.testnet.cspr.live/accounts/{PUBLIC_KEY}"
print(f"=== CSPR.live API ===")
r = requests.get(url, headers={"Accept": "application/json"}, timeout=15)
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:1000]}")

# Also try without includes
print(f"\n=== With includes ===")
url2 = f"https://api.testnet.cspr.live/accounts/{PUBLIC_KEY}?includes=account_info,centralized_account_info"
r2 = requests.get(url2, headers={"Accept": "application/json"}, timeout=15)
print(f"Status: {r2.status_code}")
print(f"Body: {r2.text[:1000]}")
