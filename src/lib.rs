//! # PayMesh — On-chain core for the agent-to-agent service marketplace.
//!
//! PayMesh is a decentralized marketplace where AI agents discover services,
//! pay per-call using the [x402](https://x402.org) HTTP-native payment
//! protocol, and settle those payments on the Casper blockchain.
//!
//! This crate contains the four smart contracts that form the on-chain
//! backbone of PayMesh:
//!
//! - [`crate::service_registry::ServiceRegistry`] — agents register the
//!   services they offer (name, endpoint, price, stake).
//! - [`crate::staking::Staking`] — providers lock CSPR to list services;
//!   misbehaviour can be slashed.
//! - [`crate::settlement::Settlement`] — verified x402 payments are recorded
//!   on-chain and revenue is tallied per provider.
//! - [`crate::reputation::Reputation`] — consumers rate services; the
//!   contract maintains an on-chain aggregate score.
//!
//! Each contract is independently deployable on Casper and is fully covered by
//! the integration tests in `tests/`.
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]

extern crate alloc;

pub mod shared;
pub mod service_registry;
pub mod staking;
pub mod settlement;
pub mod reputation;

#[cfg(test)]
mod paymesh_tests;
