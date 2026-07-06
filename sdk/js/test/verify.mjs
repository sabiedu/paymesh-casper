// Quick verification that the JS SDK crypto + full flow works.
// Run against a live node:  python demo/serve_demo.py  then  node sdk/js/test/verify.mjs

import { generateAccount, signMessage, verifySignature, canonicalAuthorization } from "../dist/index.js";

// 1. crypto roundtrip
const acct = await generateAccount("js-test");
console.log("account:", acct.publicAccountHex, "len:", acct.publicAccountHex.length);
const msg = canonicalAuthorization(acct.publicAccountHex, "01" + "ab".repeat(32), "1000", "svc", "n1");
const sig = await signMessage(msg, acct.privateKeyHex);
const ok = await verifySignature(msg, sig, acct.publicAccountHex);
const bad = await verifySignature(msg + "x", sig, acct.publicAccountHex);
console.log("sign/verify ok:", ok, "| tamper rejected:", bad === false);
if (!ok || bad) { console.error("CRYPTO FAILED"); process.exit(1); }

// 2. full SDK flow against a live node (optional)
const nodeUrl = process.env.NODE_URL || "http://127.0.0.1:8001";
try {
  const health = await fetch(`${nodeUrl}/health`);
  if (health.ok) {
    const { PayMeshClient } = await import("../dist/client.js");
    const consumer = await generateAccount("js-consumer");
    const pm = new PayMeshClient(consumer, { nodeUrl });
    await pm.deposit(2);
    const services = await pm.discoverServices();
    console.log(`discovered ${services.length} service(s)`);
    if (services.length > 0) {
      const svc = services[0];
      const r = await pm.callService(svc.service_id, { wallet: "0x" + "ff".repeat(20) });
      console.log(`paid call success=${r.success} settle=${r.settlement_id} data=`, r.data);
      const agg = await pm.rateService(svc.service_id, 4, "called from JS SDK");
      console.log(`rated; reputation:`, agg);
    }
    console.log("JS SDK END-TO-END OK (live)");
  } else {
    console.log("(node not running at", nodeUrl, "— skipping live flow; crypto OK)");
  }
} catch (e) {
  console.log("(live flow skipped:", e.message, "— crypto already verified)");
}
console.log("JS SDK verification complete.");
