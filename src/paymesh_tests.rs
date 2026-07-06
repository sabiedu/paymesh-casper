//! Integration tests for all four PayMesh contracts.
//!
//! These run against the in-process OdraVM (or the Casper test VM if
//! `ODRA_BACKEND=casper`), exercising the full register → stake → pay → rate
//! lifecycle end to end.

#![cfg(test)]

use std::panic::{catch_unwind, AssertUnwindSafe};

use crate::reputation::Reputation;
use crate::service_registry::ServiceRegistry;
use crate::settlement::Settlement;
use crate::staking::Staking;
use odra::casper_types::U512;
use odra::host::{Deployer, NoArgs};
use odra::prelude::*;

/// 1 CSPR, in motes.
const ONE_CSPR: u64 = 1_000_000_000;

#[test]
fn registry_register_get_list_deregister() {
    let env = odra_test::env();
    let provider = env.get_account(1);

    env.set_caller(provider);
    let registry = ServiceRegistry::deploy(&env, NoArgs);

    registry.register_service(
        "risk-score-api".into(),
        "Risk Score API".into(),
        "https://provider.paymesh.io".into(),
        U512::from(50_000_000), // 0.05 CSPR
        U512::from(5 * ONE_CSPR)
    );
    registry.register_service(
        "sentiment-api".into(),
        "Sentiment API".into(),
        "https://provider.paymesh.io/sent".into(),
        U512::from(20_000_000),
        U512::from(2 * ONE_CSPR)
    );

    assert_eq!(registry.service_count(), 2);

    let svc = registry.get_service("risk-score-api".into());
    assert_eq!(svc.provider, provider);
    assert_eq!(svc.name, "Risk Score API");
    assert_eq!(svc.price_per_call, U512::from(50_000_000));
    assert!(svc.active);

    let all = registry.list_services();
    assert_eq!(all.len(), 2);
    assert_eq!(registry.list_service_ids(), vec!["risk-score-api".into(), "sentiment-api".into()]);

    let by_provider = registry.get_services_by_provider(provider);
    assert_eq!(by_provider.len(), 2);

    // Deregister flips active to false but keeps the record.
    registry.deregister_service("risk-score-api".into());
    let dormant = registry.get_service("risk-score-api".into());
    assert!(!dormant.active);

    // Re-registering the same id must fail.
    let again = catch_unwind(AssertUnwindSafe(|| {
        registry.register_service(
            "sentiment-api".into(),
            "dup".into(),
            "x".into(),
            U512::from(1),
            U512::from(1)
        )
    }));
    assert!(again.is_err(), "expected re-register to revert");
}

#[test]
fn registry_access_control() {
    let env = odra_test::env();
    let provider = env.get_account(1);
    let other = env.get_account(2);

    env.set_caller(provider);
    let registry = ServiceRegistry::deploy(&env, NoArgs);
    registry.register_service(
        "svc".into(),
        "S".into(),
        "e".into(),
        U512::from(1),
        U512::from(ONE_CSPR)
    );

    // A different account cannot deregister someone else's service.
    env.set_caller(other);
    let blocked = catch_unwind(AssertUnwindSafe(|| {
        registry.deregister_service("svc".into())
    }));
    assert!(blocked.is_err(), "non-provider should not be able to deregister");
}

#[test]
fn staking_deposit_withdraw_slash() {
    let env = odra_test::env();
    let owner = env.get_account(0);
    let provider = env.get_account(1);

    env.set_caller(owner);
    let staking = Staking::deploy(&env, NoArgs);
    // Make the cooldown short for the test so we don't have to wait.
    staking.set_cooldown_period(10);

    env.set_caller(provider);
    let before = env.balance_of(&provider);

    // Stake 2 CSPR (payable).
    staking
        .with_tokens(U512::from(2 * ONE_CSPR))
        .stake("risk-api".into());

    let info = staking.get_stake("risk-api".into());
    assert_eq!(info.amount, U512::from(2 * ONE_CSPR));
    assert_eq!(info.provider, provider);
    assert_eq!(staking.get_total_staked(), U512::from(2 * ONE_CSPR));
    assert!(staking.is_bonded("risk-api".into()));
    assert_eq!(env.balance_of(&provider), before - U512::from(2 * ONE_CSPR));

    // Top up.
    staking
        .with_tokens(U512::from(ONE_CSPR))
        .stake("risk-api".into());
    assert_eq!(staking.get_stake("risk-api".into()).amount, U512::from(3 * ONE_CSPR));

    // Withdrawal requires request + cooldown.
    let no_wait = catch_unwind(AssertUnwindSafe(|| {
        staking.withdraw_stake("risk-api".into())
    }));
    assert!(no_wait.is_err(), "should not be able to withdraw without a pending request");

    staking.request_withdraw("risk-api".into());
    env.advance_block_time(11);
    staking.withdraw_stake("risk-api".into());

    assert_eq!(staking.get_stake("risk-api".into()).amount, U512::zero());
    assert_eq!(env.balance_of(&provider), before); // got it all back
}

#[test]
fn staking_slash_by_owner() {
    let env = odra_test::env();
    let owner = env.get_account(0);
    let provider = env.get_account(1);

    env.set_caller(owner);
    let staking = Staking::deploy(&env, NoArgs);

    env.set_caller(provider);
    staking
        .with_tokens(U512::from(5 * ONE_CSPR))
        .stake("bad-svc".into());

    // Only owner can slash.
    let not_owner = catch_unwind(AssertUnwindSafe(|| {
        staking.slash("bad-svc".into(), U512::from(ONE_CSPR), "x".into())
    }));
    assert!(not_owner.is_err(), "non-owner should not slash");

    env.set_caller(owner);
    staking.slash("bad-svc".into(), U512::from(2 * ONE_CSPR), "served garbage".into());
    assert_eq!(staking.get_stake("bad-svc".into()).amount, U512::from(3 * ONE_CSPR));
    assert_eq!(staking.get_stake("bad-svc".into()).slashed_total, U512::from(2 * ONE_CSPR));

    // Cannot slash more than the stake.
    let too_much = catch_unwind(AssertUnwindSafe(|| {
        staking.slash("bad-svc".into(), U512::from(100 * ONE_CSPR), "x".into())
    }));
    assert!(too_much.is_err(), "should not slash more than available");
}

#[test]
fn settlement_records_and_tallies() {
    let env = odra_test::env();
    let owner = env.get_account(0);
    let recorder = env.get_account(1);
    let payer = env.get_account(2);
    let provider = env.get_account(3);

    env.set_caller(owner);
    let settlement = Settlement::deploy(&env, NoArgs);
    settlement.add_recorder(recorder);

    // Unauthorized caller cannot record.
    env.set_caller(payer);
    let blocked = catch_unwind(AssertUnwindSafe(|| {
        settlement.record_payment(
            payer,
            provider,
            "svc".into(),
            U512::from(ONE_CSPR),
            "proof".into()
        )
    }));
    assert!(blocked.is_err(), "non-recorder should not record payments");

    env.set_caller(recorder);
    settlement.record_payment(
        payer,
        provider,
        "risk-api".into(),
        U512::from(ONE_CSPR),
        "sig-abc".into()
    );
    settlement.record_payment(
        payer,
        provider,
        "risk-api".into(),
        U512::from(2 * ONE_CSPR),
        "sig-def".into()
    );

    assert_eq!(settlement.total_payments(), 2);
    assert_eq!(settlement.get_revenue(provider), U512::from(3 * ONE_CSPR));
    assert_eq!(settlement.get_payment_count_for(provider), 2);

    let history = settlement.get_payment_history("risk-api".into());
    assert_eq!(history.len(), 2);
    assert_eq!(history[0].amount, U512::from(ONE_CSPR));
    assert_eq!(history[0].payment_proof, "sig-abc");
    assert_eq!(history[1].payer, payer);

    let recent = settlement.recent_payments(1);
    assert_eq!(recent.len(), 1);
    assert_eq!(recent[0].amount, U512::from(2 * ONE_CSPR));

    assert_eq!(settlement.get_payment(0).unwrap().index, 0);
}

#[test]
fn reputation_aggregates_and_rerates() {
    let env = odra_test::env();
    let r1 = env.get_account(1);
    let r2 = env.get_account(2);
    let r3 = env.get_account(3);

    let reputation = Reputation::deploy(&env, NoArgs);

    env.set_caller(r1);
    reputation.update_reputation("risk-api".into(), 5, "great".into());
    env.set_caller(r2);
    reputation.update_reputation("risk-api".into(), 3, "ok".into());
    env.set_caller(r3);
    reputation.update_reputation("risk-api".into(), 4, "good".into());

    let agg = reputation.get_reputation("risk-api".into());
    assert_eq!(agg.count, 3);
    assert_eq!(agg.total_score, 12);
    // average = 12/3 * 10000 = 40000 (4.00 stars)
    assert_eq!(agg.average, 40_000);

    let reviews = reputation.get_reviews("risk-api".into());
    assert_eq!(reviews.len(), 3);

    // Re-rating by r2 replaces (3 -> 5): total becomes 14, avg = 4.6667.
    env.set_caller(r2);
    reputation.update_reputation("risk-api".into(), 5, "updated".into());
    let agg2 = reputation.get_reputation("risk-api".into());
    assert_eq!(agg2.count, 3, "re-rating must not bump the count");
    assert_eq!(agg2.total_score, 14);

    // Invalid ratings revert.
    env.set_caller(r1);
    let bad_zero = catch_unwind(AssertUnwindSafe(|| {
        reputation.update_reputation("risk-api".into(), 0, "".into())
    }));
    assert!(bad_zero.is_err());
    let bad_six = catch_unwind(AssertUnwindSafe(|| {
        reputation.update_reputation("risk-api".into(), 6, "".into())
    }));
    assert!(bad_six.is_err());

    assert_eq!(reputation.total_reviews(), 3);
}

#[test]
fn full_marketplace_lifecycle() {
    // End-to-end: register -> stake -> pay (settle) -> rate, across all 4 contracts.
    let env = odra_test::env();
    let owner = env.get_account(0);
    let provider = env.get_account(1);
    let consumer = env.get_account(2);

    env.set_caller(owner);
    let registry = ServiceRegistry::deploy(&env, NoArgs);
    let staking = Staking::deploy(&env, NoArgs);
    let settlement = Settlement::deploy(&env, NoArgs);
    let reputation = Reputation::deploy(&env, NoArgs);
    settlement.add_recorder(owner);

    // Provider registers + stakes.
    env.set_caller(provider);
    registry.register_service(
        "risk-score-api-v1".into(),
        "Risk Score API".into(),
        "https://provider.paymesh.io".into(),
        U512::from(50_000_000),
        U512::from(5 * ONE_CSPR)
    );
    staking
        .with_tokens(U512::from(10 * ONE_CSPR))
        .stake("risk-score-api-v1".into());
    assert!(staking.is_bonded("risk-score-api-v1".into()));

    // Consumer pays (recorded by the gateway / owner as recorder).
    env.set_caller(owner);
    settlement.record_payment(
        consumer,
        provider,
        "risk-score-api-v1".into(),
        U512::from(50_000_000),
        "x402-sig-deadbeef".into()
    );

    // Consumer rates the service.
    env.set_caller(consumer);
    reputation.update_reputation("risk-score-api-v1".into(), 5, "blazing fast".into());

    // Push the reputation snapshot back into the registry for cheap reads.
    env.set_caller(owner);
    let agg = reputation.get_reputation("risk-score-api-v1".into());
    registry.update_reputation_snapshot(
        "risk-score-api-v1".into(),
        agg.average,
        agg.count
    );

    let final_svc = registry.get_service("risk-score-api-v1".into());
    assert!(final_svc.active);
    assert_eq!(final_svc.reputation_score, 50_000); // 5.00 stars
    assert_eq!(final_svc.total_ratings, 1);
    assert_eq!(settlement.get_revenue(provider), U512::from(50_000_000));
    assert_eq!(staking.get_stake("risk-score-api-v1".into()).amount, U512::from(10 * ONE_CSPR));
}
