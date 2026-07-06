//! Shared types used across the PayMesh contracts.
//!
//! Defining [`ServiceInfo`] here keeps the canonical service record in one
//! place: the registry owns it, but the SDK, gateway and dashboard all decode
//! the same on-chain layout.

use odra::casper_types::U512;
use odra::prelude::*;

/// A marketplace service registered by a provider agent.
///
/// Stored under its `service_id` in the [`crate::service_registry::ServiceRegistry`].
/// The reputation and stake figures here are a denormalised *snapshot* — the
/// authoritative numbers live in the [`crate::reputation::Reputation`] and
/// [`crate::staking::Staking`] contracts respectively — kept up to date so the
/// dashboard can render a service in a single read.
#[odra::odra_type]
pub struct ServiceInfo {
    /// Opaque, provider-chosen identifier (e.g. `risk-score-api-v1`).
    pub service_id: String,
    /// The agent / company that owns the service.
    pub provider: Address,
    /// Human-readable name shown in the marketplace.
    pub name: String,
    /// Base URL the resource server answers on (e.g. `https://provider.paymesh.io`).
    pub endpoint: String,
    /// Price charged per successful call, in motes (1 CSPR = 10⁹ motes).
    pub price_per_call: U512,
    /// Minimum stake (motes) required for the service to be considered active.
    pub staking_amount: U512,
    /// Latest aggregate reputation score, basis points of an average (0–50000
    /// ⇒ 0.00–5.00).
    pub reputation_score: u32,
    /// Number of ratings that produced `reputation_score`.
    pub total_ratings: u32,
    /// `true` while the service is listed and available for calls.
    pub active: bool,
    /// Block-time (seconds) at which the service was registered.
    pub registered_at: u64,
}

impl ServiceInfo {
    /// A fresh record for a brand-new listing.
    pub fn new(
        service_id: String,
        provider: Address,
        name: String,
        endpoint: String,
        price_per_call: U512,
        staking_amount: U512,
        now: u64
    ) -> Self {
        Self {
            service_id,
            provider,
            name,
            endpoint,
            price_per_call,
            staking_amount,
            reputation_score: 0,
            total_ratings: 0,
            active: true,
            registered_at: now
        }
    }
}
