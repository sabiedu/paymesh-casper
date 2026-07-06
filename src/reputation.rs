//! Reputation contract.
//!
//! After a consumer agent receives a service over x402, it can rate it with
//! [`Reputation::update_reputation`]. The contract keeps every review and
//! maintains a running aggregate so a marketplace browser can show a score
//! without scanning the full review history.
//!
//! To avoid dust-spam, each `(reviewer, service)` pair may rate at most once;
//! re-rating replaces the previous score.

use odra::prelude::*;

/// Emitted when a consumer rates a service.
#[odra::event]
pub struct ReputationUpdated {
    pub service_id: String,
    pub reviewer: Address,
    pub rating: u32,
    pub new_average: u32
}

/// Running aggregate for a service.
#[odra::odra_type]
#[derive(Default)]
pub struct RatingAggregate {
    /// Sum of all current ratings.
    pub total_score: u64,
    /// Number of ratings behind `total_score`.
    pub count: u32,
    /// Average rating in basis points of a star (0–50000 ⇒ 0.00–5.00).
    pub average: u32
}

/// A single review.
#[odra::odra_type]
pub struct Review {
    pub index: u32,
    pub service_id: String,
    pub reviewer: Address,
    /// 1–5, inclusive.
    pub rating: u32,
    pub review: String,
    pub timestamp: u64
}

/// Errors raised by the Reputation contract.
#[odra::odra_error]
pub enum ReputationError {
    InvalidRating = 1,
    InvalidServiceId = 2,
    ReviewTooLong = 3
}

/// Maximum review text length (keeps storage bounded).
pub const MAX_REVIEW_LEN: usize = 512;

/// The Reputation module.
#[odra::module]
pub struct Reputation {
    /// service_id → running aggregate.
    aggregates: Mapping<String, RatingAggregate>,
    /// Append-only review log.
    reviews: List<Review>,
    /// service_id → review indices.
    service_reviews: Mapping<String, Vec<u32>>,
    /// (reviewer, service_id) → existing review index (one rating per pair).
    rated: Mapping<(Address, String), u32>
}

#[odra::module]
impl Reputation {
    /// Constructor — nothing to seed, but required by the module system.
    pub fn init(&mut self) {}

    /// Rate a service (1–5) with an optional review.
    ///
    /// If the caller has already rated this service, their previous rating is
    /// replaced (the aggregate is adjusted, not double-counted).
    pub fn update_reputation(&mut self, service_id: String, rating: u32, review: String) {
        if rating < 1 || rating > 5 {
            self.env().revert(ReputationError::InvalidRating);
        }
        if service_id.is_empty() {
            self.env().revert(ReputationError::InvalidServiceId);
        }
        if review.len() > MAX_REVIEW_LEN {
            self.env().revert(ReputationError::ReviewTooLong);
        }

        let reviewer = self.env().caller();
        let now = self.env().get_block_time();
        let key = (reviewer, service_id.clone());

        // Adjust the aggregate, accounting for a possible re-rating.
        let mut agg = self.aggregates.get(&service_id).unwrap_or_default();
        match self.rated.get(&key) {
            Some(prev_index) => {
                if let Some(prev) = self.reviews.get(prev_index) {
                    // Roll back the old score, then apply the new one.
                    agg.total_score = agg
                        .total_score
                        .saturating_sub(prev.rating as u64)
                        + rating as u64;
                    let new_review = Review {
                        index: prev_index,
                        service_id: service_id.clone(),
                        reviewer,
                        rating,
                        review,
                        timestamp: now
                    };
                    self.reviews.replace(prev_index, new_review);
                }
            }
            None => {
                let index = self.reviews.len();
                agg.total_score += rating as u64;
                agg.count += 1;
                self.reviews.push(Review {
                    index,
                    service_id: service_id.clone(),
                    reviewer,
                    rating,
                    review,
                    timestamp: now
                });

                let mut svc = self.service_reviews.get(&service_id).unwrap_or_default();
                svc.push(index);
                self.service_reviews.set(&service_id, svc);
                self.rated.set(&key, index);
            }
        }
        agg.average = if agg.count == 0 {
            0
        } else {
            // basis points of a star: avg * 10000
            ((agg.total_score as u128) * 10_000 / agg.count as u128) as u32
        };
        self.aggregates.set(&service_id, agg.clone());

        self.env().emit_event(ReputationUpdated {
            service_id,
            reviewer,
            rating,
            new_average: agg.average
        });
    }

    /// The running aggregate for a service.
    pub fn get_reputation(&self, service_id: String) -> RatingAggregate {
        self.aggregates.get(&service_id).unwrap_or_default()
    }

    /// All reviews for a service, oldest first.
    pub fn get_reviews(&self, service_id: String) -> Vec<Review> {
        let indices = self.service_reviews.get(&service_id).unwrap_or_default();
        let mut out = Vec::with_capacity(indices.len());
        for i in indices {
            if let Some(r) = self.reviews.get(i) {
                out.push(r);
            }
        }
        out
    }

    /// Total reviews across the whole marketplace.
    pub fn total_reviews(&self) -> u32 {
        self.reviews.len()
    }
}
