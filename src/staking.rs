//! Staking contract.
//!
//! Providers lock CSPR to back their services. A stake is slashing collateral:
//! if a provider misbehaves (serves garbage, is offline, etc.) governance can
//! [`Staking::slash`] part of it. Stakes are time-locked — a provider requests
//! withdrawal, waits out `cooldown_period`, then claims the CSPR back.
//!
//! CSPR is moved with the call: [`Staking::stake`] is `#[odra(payable)]` and
//! reads [`ContractEnv::attached_value`](odra::ContractEnv::attached_value);
//! [`Staking::withdraw_stake`] pays out with
//! [`ContractEnv::transfer_tokens`](odra::ContractEnv::transfer_tokens).

use odra::casper_types::U512;
use odra::prelude::*;

/// Emitted when a provider locks stake.
#[odra::event]
pub struct Staked {
    pub service_id: String,
    pub provider: Address,
    pub amount: U512,
    pub new_total: U512
}

/// Emitted when a provider requests an unlock (starts the cooldown).
#[odra::event]
pub struct WithdrawRequested {
    pub service_id: String,
    pub provider: Address,
    pub unlock_at: u64
}

/// Emitted when stake is paid back to the provider.
#[odra::event]
pub struct Withdrawn {
    pub service_id: String,
    pub provider: Address,
    pub amount: U512
}

/// Emitted when governance seizes part of a stake.
#[odra::event]
pub struct Slashed {
    pub service_id: String,
    pub provider: Address,
    pub amount: U512,
    pub reason: String
}

/// On-chain record of a single service's stake.
#[odra::odra_type]
pub struct StakeInfo {
    pub provider: Address,
    pub amount: U512,
    pub staked_at: u64,
    /// 0 while locked; set to the timestamp when withdrawal becomes allowed.
    pub unlock_at: u64,
    /// Lifetime CSPR seized from this stake.
    pub slashed_total: U512
}

/// Errors raised by the Staking contract.
#[odra::odra_error]
pub enum StakingError {
    NotAuthorized = 1,
    StakeNotFound = 2,
    /// Tried to withdraw while still locked / no pending request.
    WithdrawLocked = 3,
    /// Tried to stake 0 CSPR.
    ZeroAmount = 4,
    /// Slash amount exceeds the current stake.
    InsufficientStake = 5,
    /// Only the original provider may withdraw.
    NotProvider = 6
}

/// 24 hours, in seconds — the default withdrawal cooldown.
pub const DEFAULT_COOLDOWN_SECS: u64 = 86_400;

/// The Staking module.
#[odra::module]
pub struct Staking {
    /// service_id → stake record.
    stakes: Mapping<String, StakeInfo>,
    /// Withdrawal cooldown window (seconds).
    cooldown_period: Var<u64>,
    /// Minimum stake (motes) to be considered bonded.
    min_stake: Var<U512>,
    /// Deployer / governance — the only address that may slash.
    owner: Var<Address>,
    /// Running total of all live stakes (motes).
    total_staked: Var<U512>
}

#[odra::module]
impl Staking {
    /// Constructor — sets sensible defaults and records the deployer as owner.
    pub fn init(&mut self) {
        self.owner.set(self.env().caller());
        self.cooldown_period.set(DEFAULT_COOLDOWN_SECS);
        // 1 CSPR minimum (1e9 motes).
        self.min_stake.set(U512::from(1_000_000_000u64));
        self.total_staked.set(U512::zero());
    }

    /// Governance: change the withdrawal cooldown.
    pub fn set_cooldown_period(&mut self, secs: u64) {
        self.assert_owner();
        self.cooldown_period.set(secs);
    }

    /// Governance: change the minimum stake.
    pub fn set_min_stake(&mut self, amount: U512) {
        self.assert_owner();
        self.min_stake.set(amount);
    }

    /// Transfer ownership (and thus the slashing authority).
    pub fn transfer_ownership(&mut self, new_owner: Address) {
        self.assert_owner();
        self.owner.set(new_owner);
    }

    /// Lock CSPR behind a service. **Payable** — attach CSPR to the call.
    ///
    /// Top-ups are allowed: calling `stake` again on an existing, still-locked
    /// position adds to the amount and resets `unlock_at` to 0 (re-locks).
    #[odra(payable)]
    pub fn stake(&mut self, service_id: String) {
        let amount = self.env().attached_value();
        if amount.is_zero() {
            self.env().revert(StakingError::ZeroAmount);
        }

        let provider = self.env().caller();
        let now = self.env().get_block_time();

        let new_record = match self.stakes.get(&service_id) {
            Some(mut existing) => {
                if existing.provider != provider {
                    self.env().revert(StakingError::NotProvider);
                }
                existing.amount = existing.amount + amount;
                existing.unlock_at = 0; // re-lock on top-up
                existing
            }
            None => {
                if amount < self.min_stake.get_or_default() {
                    self.env().revert(StakingError::ZeroAmount);
                }
                StakeInfo {
                    provider,
                    amount,
                    staked_at: now,
                    unlock_at: 0,
                    slashed_total: U512::zero()
                }
            }
        };

        let total = new_record.amount;
        self.stakes.set(&service_id, new_record.clone());
        self.total_staked.set(self.total_staked.get_or_default() + amount);

        self.env().emit_event(Staked {
            service_id,
            provider,
            amount,
            new_total: total
        });
    }

    /// Begin the withdrawal cooldown. After it elapses, [`Self::withdraw_stake`]
    /// pays the CSPR back to the provider.
    pub fn request_withdraw(&mut self, service_id: String) {
        let mut info = self
            .stakes
            .get(&service_id)
            .unwrap_or_revert_with(self, StakingError::StakeNotFound);

        if info.provider != self.env().caller() {
            self.env().revert(StakingError::NotProvider);
        }

        let cooldown = self.cooldown_period.get_or_default();
        info.unlock_at = self.env().get_block_time() + cooldown;
        self.stakes.set(&service_id, info.clone());

        self.env().emit_event(WithdrawRequested {
            service_id,
            provider: info.provider,
            unlock_at: info.unlock_at
        });
    }

    /// Pay the stake back to the provider, after the cooldown has elapsed.
    pub fn withdraw_stake(&mut self, service_id: String) {
        let info = self
            .stakes
            .get(&service_id)
            .unwrap_or_revert_with(self, StakingError::StakeNotFound);

        if info.provider != self.env().caller() {
            self.env().revert(StakingError::NotProvider);
        }
        if info.unlock_at == 0 || self.env().get_block_time() < info.unlock_at {
            self.env().revert(StakingError::WithdrawLocked);
        }

        let payout = info.amount;
        self.total_staked.set(self.total_staked.get_or_default().saturating_sub(payout));
        // Clear the record: stake fully withdrawn.
        self.stakes.set(&service_id, StakeInfo {
            provider: info.provider,
            amount: U512::zero(),
            staked_at: info.staked_at,
            unlock_at: 0,
            slashed_total: info.slashed_total
        });

        self.env().transfer_tokens(&info.provider, &payout);

        self.env().emit_event(Withdrawn {
            service_id,
            provider: info.provider,
            amount: payout
        });
    }

    /// Governance only — seize `amount` motes from a stake.
    ///
    /// The seized CSPR stays in the contract (a separate `collect_slashed`
    /// sweep could move it to a treasury). `reason` is recorded on-chain so
    /// the slash is auditable.
    pub fn slash(&mut self, service_id: String, amount: U512, reason: String) {
        self.assert_owner();

        let mut info = self
            .stakes
            .get(&service_id)
            .unwrap_or_revert_with(self, StakingError::StakeNotFound);

        if amount > info.amount {
            self.env().revert(StakingError::InsufficientStake);
        }
        info.amount = info.amount - amount;
        info.slashed_total = info.slashed_total + amount;
        self.stakes.set(&service_id, info.clone());

        self.env().emit_event(Slashed {
            service_id,
            provider: info.provider,
            amount,
            reason
        });
    }

    /// Read the stake record for a service.
    pub fn get_stake(&self, service_id: String) -> StakeInfo {
        self.stakes
            .get(&service_id)
            .unwrap_or_revert_with(self, StakingError::StakeNotFound)
    }

    /// `true` if a service is bonded at or above the minimum.
    pub fn is_bonded(&self, service_id: String) -> bool {
        match self.stakes.get(&service_id) {
            Some(info) => info.amount >= self.min_stake.get_or_default(),
            None => false
        }
    }

    /// Aggregate CSPR currently locked across all services.
    pub fn get_total_staked(&self) -> U512 {
        self.total_staked.get_or_default()
    }

    /// CSPR currently held by this contract.
    pub fn contract_balance(&self) -> U512 {
        self.env().self_balance()
    }

    /// The configured cooldown (seconds).
    pub fn get_cooldown_period(&self) -> u64 {
        self.cooldown_period.get_or_default()
    }

    fn is_owner(&self) -> bool {
        self.owner.get().map_or(false, |o| o == self.env().caller())
    }

    fn assert_owner(&self) {
        if !self.is_owner() {
            self.env().revert(StakingError::NotAuthorized);
        }
    }
}
