import type { ServiceInfo } from "../types";

function short(s: string, n = 10): string {
  return s.length > n ? `${s.slice(0, n)}…${s.slice(-4)}` : s;
}

function Stars({ rating }: { rating: number }) {
  const full = Math.round(rating);
  return (
    <span className="stars" title={`${rating.toFixed(2)} / 5`}>
      {"★".repeat(full)}
      {"☆".repeat(5 - full)}
    </span>
  );
}

export default function ServiceCard({
  svc,
  onClick,
  selected,
}: {
  svc: ServiceInfo;
  onClick: () => void;
  selected: boolean;
}) {
  const stake = svc.stake_amount_cspr ?? svc.staking_amount_cspr ?? 0;
  return (
    <div
      className={`card service ${selected ? "selected" : ""} ${svc.active ? "" : "inactive"}`}
      onClick={onClick}
    >
      <div className="service-head">
        <span className="dot" data-active={svc.active} />
        <h3>{svc.name}</h3>
      </div>
      <code className="service-id">{svc.service_id}</code>
      <div className="service-grid">
        <div className="metric">
          <span className="label">Price / call</span>
          <span className="value">{svc.price_per_call_cspr.toFixed(4)} CSPR</span>
        </div>
        <div className="metric">
          <span className="label">Stake</span>
          <span className="value">{stake.toFixed(2)} CSPR</span>
        </div>
        <div className="metric">
          <span className="label">Reputation</span>
          <span className="value">
            <Stars rating={svc.average_rating} />{" "}
            <span className="muted">({svc.total_ratings})</span>
          </span>
        </div>
      </div>
      <div className="provider">
        <span className="label">Provider</span>
        <code>{short(svc.provider, 14)}</code>
      </div>
    </div>
  );
}
