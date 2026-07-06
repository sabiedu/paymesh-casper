import type { PaymentRecord } from "../types";

function short(s: string, n = 10): string {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

function timeAgo(ts: number): string {
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function TransactionFeed({
  payments,
}: {
  payments: PaymentRecord[];
}) {
  return (
    <div className="card feed">
      <div className="card-title">
        <h3>Live Settlement Feed</h3>
        <span className="badge">{payments.length}</span>
      </div>
      {payments.length === 0 ? (
        <p className="empty">No settlements yet. Run the demo to see x402 payments land here.</p>
      ) : (
        <ul className="tx-list">
          {payments.map((p) => (
            <li key={p.index} className="tx">
              <div className="tx-main">
                <span className="tx-amount">+{(p.amount_motes / 1e9).toFixed(4)} CSPR</span>
                <span className="tx-svc">{p.service_id}</span>
              </div>
              <div className="tx-meta">
                <span>{short(p.payer, 8)}</span>
                <span className="arrow">→</span>
                <span>{short(p.provider, 8)}</span>
              </div>
              <span className="tx-time">{timeAgo(p.timestamp)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
