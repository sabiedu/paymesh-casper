//! Service Registry contract.
//!
//! The Service Registry is the discovery layer of PayMesh. Provider agents call
//! [`ServiceRegistry::register_service`] to publish what they offer; consumer
//! agents call [`ServiceRegistry::list_services`] / [`ServiceRegistry::get_service`]
//! to discover and inspect listings.
//!
//! Each listing is keyed by a provider-chosen `service_id` and stores the full
//! [`ServiceInfo`] record. The registry additionally indexes listings by their
//! provider address so a dashboard can show "all services from this agent".

use crate::shared::ServiceInfo;
use odra::casper_types::U512;
use odra::prelude::*;

/// Emitted when a provider publishes a new service.
#[odra::event]
pub struct ServiceRegistered {
    pub service_id: String,
    pub provider: Address,
    pub price_per_call: U512
}

/// Emitted when a provider takes a service down.
#[odra::event]
pub struct ServiceDeregistered {
    pub service_id: String,
    pub provider: Address
}

/// Emitted when a service's reputation snapshot is refreshed from the
/// Reputation contract (called by an authorised relayer / the gateway).
#[odra::event]
pub struct ReputationSnapshotUpdated {
    pub service_id: String,
    pub reputation_score: u32,
    pub total_ratings: u32
}

/// Errors raised by the Service Registry.
#[odra::odra_error]
pub enum RegistryError {
    /// A service with the given id is already registered.
    ServiceAlreadyExists = 1,
    /// No service with the given id exists.
    ServiceNotFound = 2,
    /// The caller is not allowed to perform this action (not the owner).
    NotAuthorized = 3,
    /// The service id was empty or too long.
    InvalidServiceId = 4,
    /// The caller is not the provider of the service.
    NotProvider = 5
}

/// The Service Registry module.
#[odra::module]
pub struct ServiceRegistry {
    /// service_id → full record.
    services: Mapping<String, ServiceInfo>,
    /// Every registered id, in insertion order (for cheap listing).
    service_ids: List<String>,
    /// provider address → list of their service ids.
    provider_services: Mapping<Address, Vec<String>>,
    /// Deployer / admin who may refresh reputation snapshots.
    owner: Var<Address>,
    /// Addresses authorised to push reputation snapshots (e.g. the gateway).
    relayers: Mapping<Address, bool>
}

#[odra::module]
impl ServiceRegistry {
    /// Constructor — records the deployer as the initial owner.
    pub fn init(&mut self) {
        self.owner.set(self.env().caller());
    }

    /// Transfer ownership to a new address.
    pub fn transfer_ownership(&mut self, new_owner: Address) {
        self.assert_owner();
        self.owner.set(new_owner);
    }

    /// Whitelist an address as a relayer (may push reputation snapshots).
    pub fn add_relayer(&mut self, relayer: Address) {
        self.assert_owner();
        self.relayers.set(&relayer, true);
    }

    /// Remove a relayer.
    pub fn revoke_relayer(&mut self, relayer: Address) {
        self.assert_owner();
        self.relayers.set(&relayer, false);
    }

    /// Register a new service.
    ///
    /// `service_id` must be unique and non-empty. `price_per_call` is in motes.
    /// `staking_amount` is the minimum stake (declared here, actually locked in
    /// the separate Staking contract).
    pub fn register_service(
        &mut self,
        service_id: String,
        name: String,
        endpoint: String,
        price_per_call: U512,
        staking_amount: U512
    ) {
        if service_id.is_empty() || service_id.len() > 64 {
            self.env().revert(RegistryError::InvalidServiceId);
        }
        if self.services.get(&service_id).is_some() {
            self.env().revert(RegistryError::ServiceAlreadyExists);
        }

        let provider = self.env().caller();
        let info = ServiceInfo::new(
            service_id.clone(),
            provider,
            name,
            endpoint,
            price_per_call,
            staking_amount,
            self.env().get_block_time()
        );

        self.services.set(&service_id, info.clone());
        self.service_ids.push(service_id.clone());

        let mut owned = self.provider_services.get(&provider).unwrap_or_default();
        owned.push(service_id.clone());
        self.provider_services.set(&provider, owned);

        self.env().emit_event(ServiceRegistered {
            service_id,
            provider,
            price_per_call
        });
    }

    /// Remove a service. Only its provider may deregister it.
    pub fn deregister_service(&mut self, service_id: String) {
        let info = self
            .services
            .get(&service_id)
            .unwrap_or_revert_with(self, RegistryError::ServiceNotFound);

        if info.provider != self.env().caller() {
            self.env().revert(RegistryError::NotProvider);
        }

        // Flip the active flag but keep the record for history/reputation.
        let mut updated = info.clone();
        updated.active = false;
        self.services.set(&service_id, updated);

        self.env().emit_event(ServiceDeregistered {
            service_id,
            provider: info.provider
        });
    }

    /// Re-activate a previously deregistered service.
    pub fn reactivate_service(&mut self, service_id: String) {
        let info = self
            .services
            .get(&service_id)
            .unwrap_or_revert_with(self, RegistryError::ServiceNotFound);

        if info.provider != self.env().caller() {
            self.env().revert(RegistryError::NotProvider);
        }
        let mut updated = info.clone();
        updated.active = true;
        self.services.set(&service_id, updated);
    }

    /// Push a reputation snapshot for a service. Only owner or a relayer may
    /// call this — it keeps the registry's denormalised score fresh for cheap
    /// reads by the dashboard without a cross-contract call on every query.
    pub fn update_reputation_snapshot(
        &mut self,
        service_id: String,
        reputation_score: u32,
        total_ratings: u32
    ) {
        if !self.is_owner() && !self.relayers.get(&self.env().caller()).unwrap_or_default() {
            self.env().revert(RegistryError::NotAuthorized);
        }
        let info = self
            .services
            .get(&service_id)
            .unwrap_or_revert_with(self, RegistryError::ServiceNotFound);
        let mut updated = info.clone();
        updated.reputation_score = reputation_score;
        updated.total_ratings = total_ratings;
        self.services.set(&service_id, updated);

        self.env().emit_event(ReputationSnapshotUpdated {
            service_id,
            reputation_score,
            total_ratings
        });
    }

    /// Read a single service. Reverts if it does not exist.
    pub fn get_service(&self, service_id: String) -> ServiceInfo {
        self.services
            .get(&service_id)
            .unwrap_or_revert_with(self, RegistryError::ServiceNotFound)
    }

    /// Read a single service, or `None` if absent (non-reverting lookup).
    pub fn maybe_get_service(&self, service_id: String) -> Option<ServiceInfo> {
        self.services.get(&service_id)
    }

    /// All registered services, in insertion order.
    pub fn list_services(&self) -> Vec<ServiceInfo> {
        let count = self.service_ids.len();
        let mut out = Vec::new();
        for i in 0..count {
            if let Some(id) = self.service_ids.get(i) {
                if let Some(info) = self.services.get(&id) {
                    out.push(info);
                }
            }
        }
        out
    }

    /// Just the ids (lighter than [`Self::list_services`]).
    pub fn list_service_ids(&self) -> Vec<String> {
        let count = self.service_ids.len();
        let mut out = Vec::new();
        for i in 0..count {
            if let Some(id) = self.service_ids.get(i) {
                out.push(id);
            }
        }
        out
    }

    /// Service ids owned by a given provider.
    pub fn get_services_by_provider(&self, provider: Address) -> Vec<String> {
        self.provider_services.get(&provider).unwrap_or_default()
    }

    /// How many services are currently registered.
    pub fn service_count(&self) -> u32 {
        self.service_ids.len()
    }

    /// Current owner address.
    pub fn get_owner(&self) -> Address {
        self.owner.get_or_revert_with(RegistryError::NotAuthorized)
    }

    fn is_owner(&self) -> bool {
        self.owner.get().map_or(false, |o| o == self.env().caller())
    }

    fn assert_owner(&self) {
        if !self.is_owner() {
            self.env().revert(RegistryError::NotAuthorized);
        }
    }
}
