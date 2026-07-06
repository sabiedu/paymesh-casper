//! Settlement contract.
//!
//! Once an x402 payment has been **verified** (by the gateway acting as a
//! facilitator, or by an on-chain verifier), it is recorded here so that:
//!
//! - every payment is an immutable, queryable on-chain event,
//! - a provider's lifetime revenue is tallied in a single read, and
//! - the dashboard can stream a live transaction feed.
//!
//! Only an authorised *recorder* (the PayMesh gateway, or a relayer) may call
//! [`Settlement::record_payment`], because it attests that the x402 proof was
//! valid and the resource was delivered.

use odra::casper_types::U512;
use odra::prelude::*;

/// Emitted for every settled x402 payment.
#[odra::event]
pub struct PaymentSettled {
    pub payment_index: u32,
    pub payer: Address,
    pub provider: Address,
    pub service_id: String,
    pub amount: U512,
    pub payment_proof: String
}

/// An immutable record of a single x402 payment settled on-chain.
#[odra::odra_type]
pub struct PaymentRecord {
    /// Position in the global payments list.
    pub index: u32,
    pub payer: Address,
    pub provider: Address,
    pub service_id: String,
    pub amount: U512,
    /// The x402 payment payload / settlement signature, base64.
    pub payment_proof: String,
    /// Block-time (seconds) the payment was recorded.
    pub timestamp: u64
}

/// Errors raised by the Settlement contract.
#[odra::odra_error]
pub enum SettlementError {
    NotAuthorized = 1,
    ZeroAmount = 2,
    InvalidServiceId = 3
}

/// The Settlement module.
#[odra::module]
pub struct Settlement {
    /// Append-only ledger of every payment.
    payments: List<PaymentRecord>,
    /// service_id → indices into `payments`.
    service_payments: Mapping<String, Vec<u32>>,
    /// provider address → total motes ever earned.
    provider_revenue: Mapping<Address, U512>,
    /// provider address → number of settled payments.
    provider_payment_count: Mapping<Address, u32>,
    /// Deployer / admin.
    owner: Var<Address>,
    /// Addresses authorised to record payments (the gateway / facilitators).
    recorders: Mapping<Address, bool>
}

#[odra::module]
impl Settlement {
    /// Constructor — records the deployer as owner.
    pub fn init(&mut self) {
        self.owner.set(self.env().caller());
    }

    /// Transfer ownership.
    pub fn transfer_ownership(&mut self, new_owner: Address) {
        self.assert_owner();
        self.owner.set(new_owner);
    }

    /// Authorise a recorder (gateway / facilitator).
    pub fn add_recorder(&mut self, recorder: Address) {
        self.assert_owner();
        self.recorders.set(&recorder, true);
    }

    /// Revoke a recorder.
    pub fn revoke_recorder(&mut self, recorder: Address) {
        self.assert_owner();
        self.recorders.set(&recorder, false);
    }

    /// Record a verified x402 payment.
    ///
    /// Called by an authorised recorder after it has validated the x402
    /// `PaymentPayload` and confirmed the resource was delivered. The actual
    /// CSPR movement happens off-chain via the x402 facilitator; this function
    /// is the **on-chain attestation** of that settlement.
    pub fn record_payment(
        &mut self,
        payer: Address,
        provider: Address,
        service_id: String,
        amount: U512,
        payment_proof: String
    ) {
        self.assert_recorder();

        if amount.is_zero() {
            self.env().revert(SettlementError::ZeroAmount);
        }
        if service_id.is_empty() {
            self.env().revert(SettlementError::InvalidServiceId);
        }

        let index = self.payments.len();
        let record = PaymentRecord {
            index,
            payer,
            provider,
            service_id: service_id.clone(),
            amount,
            payment_proof: payment_proof.clone(),
            timestamp: self.env().get_block_time()
        };

        self.payments.push(record.clone());

        let mut svc = self.service_payments.get(&service_id).unwrap_or_default();
        svc.push(index);
        self.service_payments.set(&service_id, svc);

        let prev_rev = self.provider_revenue.get(&provider).unwrap_or_default();
        self.provider_revenue.set(&provider, prev_rev + amount);

        let prev_cnt = self.provider_payment_count.get(&provider).unwrap_or_default();
        self.provider_payment_count.set(&provider, prev_cnt + 1);

        self.env().emit_event(PaymentSettled {
            payment_index: index,
            payer,
            provider,
            service_id,
            amount,
            payment_proof
        });
    }

    /// Total motes a provider has earned across all services.
    pub fn get_revenue(&self, provider: Address) -> U512 {
        self.provider_revenue.get(&provider).unwrap_or_default()
    }

    /// Number of settled payments for a provider.
    pub fn get_payment_count_for(&self, provider: Address) -> u32 {
        self.provider_payment_count.get(&provider).unwrap_or_default()
    }

    /// All payments for a service, oldest first.
    pub fn get_payment_history(&self, service_id: String) -> Vec<PaymentRecord> {
        let indices = self.service_payments.get(&service_id).unwrap_or_default();
        let mut out = Vec::with_capacity(indices.len());
        for i in indices {
            if let Some(rec) = self.payments.get(i) {
                out.push(rec);
            }
        }
        out
    }

    /// The most recent `limit` payments (for the dashboard's live feed).
    pub fn recent_payments(&self, limit: u32) -> Vec<PaymentRecord> {
        let total = self.payments.len();
        if total == 0 || limit == 0 {
            return Vec::new();
        }
        let start = total.saturating_sub(limit);
        let mut out = Vec::new();
        for i in start..total {
            if let Some(rec) = self.payments.get(i) {
                out.push(rec);
            }
        }
        out
    }

    /// A single payment by index, if it exists.
    pub fn get_payment(&self, index: u32) -> Option<PaymentRecord> {
        self.payments.get(index)
    }

    /// Total number of settled payments network-wide.
    pub fn total_payments(&self) -> u32 {
        self.payments.len()
    }

    fn assert_recorder(&self) {
        if !self.is_owner() && !self.recorders.get(&self.env().caller()).unwrap_or_default() {
            self.env().revert(SettlementError::NotAuthorized);
        }
    }

    fn is_owner(&self) -> bool {
        self.owner.get().map_or(false, |o| o == self.env().caller())
    }

    fn assert_owner(&self) {
        if !self.is_owner() {
            self.env().revert(SettlementError::NotAuthorized);
        }
    }
}
