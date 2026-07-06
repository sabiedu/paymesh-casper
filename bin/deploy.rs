//! PayMesh — Casper Testnet Deployment Binary
//!
//! Deploys all 4 PayMesh contracts to the Casper Testnet using Odra's
//! livenet environment (CasperClient with V1 transactions).
//!
//! Prerequisites:
//!   1. `cargo odra build`  (produces wasm/*.wasm)
//!   2. `.env` file at project root with testnet config
//!   3. Funded secret key (faucet at https://testnet.cspr.tools/)
//!
//! Run from the project root (where wasm/ and .env live):
//!   cargo run --bin paymesh_casper_deploy

use odra::host::{Deployer, NoArgs};
use odra_casper_livenet_env::env as livenet_env;
use paymesh_casper::reputation::ReputationHostRef;
use paymesh_casper::service_registry::ServiceRegistryHostRef;
use paymesh_casper::settlement::SettlementHostRef;
use paymesh_casper::staking::StakingHostRef;

const DEPLOY_GAS: u64 = 5_000_000_000; // 5 billion — generous for contract init

fn main() {
    println!("═══════════════════════════════════════════════");
    println!("  PayMesh → Casper Testnet Deployment");
    println!("═══════════════════════════════════════════════\n");

    let env = livenet_env();
    env.set_gas(DEPLOY_GAS);

    // Account 0 (the secret key holder) is the deployer/owner of all contracts.
    let deployer = env.get_account(0);
    println!("Deployer address: {:?}\n", deployer);

    // ── 1. Service Registry ──────────────────────────────────────────────
    println!("[1/4] Deploying ServiceRegistry…");
    let registry = ServiceRegistryHostRef::deploy(&env, NoArgs);
    println!("  ✅ ServiceRegistry  → {:?}", registry.address());

    // ── 2. Staking ───────────────────────────────────────────────────────
    println!("[2/4] Deploying Staking…");
    let staking = StakingHostRef::deploy(&env, NoArgs);
    println!("  ✅ Staking          → {:?}", staking.address());

    // ── 3. Settlement ────────────────────────────────────────────────────
    println!("[3/4] Deploying Settlement…");
    let settlement = SettlementHostRef::deploy(&env, NoArgs);
    println!("  ✅ Settlement       → {:?}", settlement.address());

    // ── 4. Reputation ────────────────────────────────────────────────────
    println!("[4/4] Deploying Reputation…");
    let reputation = ReputationHostRef::deploy(&env, NoArgs);
    println!("  ✅ Reputation       → {:?}", reputation.address());

    // ── Summary ──────────────────────────────────────────────────────────
    println!("\n═══════════════════════════════════════════════");
    println!("  🎉 All 4 contracts deployed!");
    println!("═══════════════════════════════════════════════");
    println!("  ServiceRegistry : {:?}", registry.address());
    println!("  Staking         : {:?}", staking.address());
    println!("  Settlement      : {:?}", settlement.address());
    println!("  Reputation      : {:?}", reputation.address());
    println!("═══════════════════════════════════════════════\n");

    // Optional: wire contracts together (add each other as relayers/recorders)
    // This is done post-deployment via owner-only calls.
    println!("Post-deploy: Call the following to wire contracts:");
    println!("  registry.add_relayer(deployer)");
    println!("  settlement.add_recorder(deployer)");
    println!("\nDone. Update the dashboard/.env with these addresses.");
}
