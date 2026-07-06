import { useState } from "react";
import { useShell, Stat } from "../components/Shell";
import ServiceCard from "../components/ServiceCard";
import TransactionFeed from "../components/TransactionFeed";
import type { MarketplaceStats } from "../types";

function StatBar({ stats }: { stats: MarketplaceStats | null }) {
  const items: { label: string; value: number | string }[] = [
    { label: "Services", value: stats?.service_count ?? 0 },
    { label: "Active", value: stats?.active_services ?? 0 },
    { label: "Staked (CSPR)", value: (stats?.total_staked_cspr ?? 0).toFixed(2) },
    { label: "Settled payments", value: stats?.total_payments ?? 0 },
    { label: "Volume (CSPR)", value: (stats?.total_volume_cspr ?? 0).toFixed(4) },
  ];
  return (
    <div className="stat-bar">
      {items.map((it) => (
        <Stat key={it.label} label={it.label} value={it.value} />
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { stats, services, payments } = useShell();
  const [selected, setSelected] = useState<string | null>(null);

  const selectedSvc = services.find((s) => s.service_id === selected) || null;

  return (
    <>
      <StatBar stats={stats} />

      <main className="grid">
        <section className="col services-col">
          <div className="col-head">
            <h2>Marketplace Services</h2>
            <span className="muted">
              {services.length} registered · click a card for details
            </span>
          </div>
          <div className="services">
            {services.length === 0 ? (
              <div className="card empty">
                <p>No services registered yet.</p>
                <p className="muted">
                  Click <code>+ List a Service</code> above, or run{" "}
                  <code>python demo/serve_demo.py</code>.
                </p>
              </div>
            ) : (
              services.map((s) => (
                <ServiceCard
                  key={s.service_id}
                  svc={s}
                  selected={s.service_id === selected}
                  onClick={() =>
                    setSelected(s.service_id === selected ? null : s.service_id)
                  }
                />
              ))
            )}
          </div>
        </section>

        <section className="col">
          <TransactionFeed payments={payments} />

          {selectedSvc && (
            <div className="card detail">
              <div className="card-title">
                <h3>{selectedSvc.name}</h3>
                <span className="badge">{selectedSvc.service_id}</span>
              </div>
              <dl className="detail-grid">
                <div>
                  <dt>Endpoint</dt>
                  <dd>
                    <code>{selectedSvc.endpoint.replace(/^https?:\/\/127\.0\.0\.1:8001/, window.location.origin)}</code>
                  </dd>
                </div>
                <div>
                  <dt>Provider</dt>
                  <dd>
                    <code>{selectedSvc.provider.slice(0, 10)}…{selectedSvc.provider.slice(-6)}</code>
                  </dd>
                </div>
                <div>
                  <dt>Price / call</dt>
                  <dd>{selectedSvc.price_per_call_cspr.toFixed(6)} CSPR</dd>
                </div>
                <div>
                  <dt>Stake</dt>
                  <dd>
                    {(
                      selectedSvc.stake_amount_cspr ?? selectedSvc.staking_amount_cspr
                    ).toFixed(3)}{" "}
                    CSPR
                  </dd>
                </div>
                <div>
                  <dt>Average rating</dt>
                  <dd>{selectedSvc.average_rating.toFixed(2)} / 5</dd>
                </div>
                <div>
                  <dt>Ratings</dt>
                  <dd>{selectedSvc.total_ratings}</dd>
                </div>
              </dl>
            </div>
          )}
        </section>
      </main>

      <footer className="footer">
        <span>
          PayMesh ·{" "}
          <a href="https://x402.org" target="_blank" rel="noreferrer">
            x402
          </a>{" "}
          ·{" "}
          <a href="https://casper.network" target="_blank" rel="noreferrer">
            Casper
          </a>{" "}
          · Odra smart contracts
        </span>
      </footer>
    </>
  );
}
