import { useCallback, useEffect, useState } from "react";
import type { MarketplaceStats, PaymentRecord, ServiceInfo } from "./types";
import { checkHealth, fetchRecentPayments, fetchServices, fetchStats, getBaseUrl, setBaseUrl } from "./api";
import ServiceCard from "./components/ServiceCard";
import TransactionFeed from "./components/TransactionFeed";

function StatBar({ stats }: { stats: MarketplaceStats | null }) {
  const items = [
    { label: "Services", value: stats?.service_count ?? 0 },
    { label: "Active", value: stats?.active_services ?? 0 },
    { label: "Staked (CSPR)", value: (stats?.total_staked_cspr ?? 0).toFixed(2) },
    { label: "Settled payments", value: stats?.total_payments ?? 0 },
    { label: "Volume (CSPR)", value: (stats?.total_volume_cspr ?? 0).toFixed(4) },
  ];
  return (
    <div className="stat-bar">
      {items.map((it) => (
        <div className="stat" key={it.label}>
          <div className="stat-value">{it.value}</div>
          <div className="stat-label">{it.label}</div>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [stats, setStats] = useState<MarketplaceStats | null>(null);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [online, setOnline] = useState(false);
  const [nodeInput, setNodeInput] = useState(getBaseUrl());

  const refresh = useCallback(async () => {
    const [ok, s, sv, pay] = await Promise.all([
      checkHealth(),
      fetchStats().catch(() => null),
      fetchServices().catch(() => []),
      fetchRecentPayments(25).catch(() => []),
    ]);
    setOnline(ok);
    if (s) setStats(s);
    setServices(sv);
    setPayments(pay);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 2500);
    return () => clearInterval(id);
  }, [refresh]);

  const applyNode = () => {
    setBaseUrl(nodeInput.trim());
    refresh();
  };

  const selectedSvc = services.find((s) => s.service_id === selected) || null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◆</span>
          <div>
            <h1>PayMesh</h1>
            <p className="tagline">x402 agent marketplace on Casper</p>
          </div>
        </div>
        <div className="node-form">
          <span className={`status ${online ? "ok" : "down"}`}>● {online ? "node online" : "node offline"}</span>
          <input
            value={nodeInput}
            onChange={(e) => setNodeInput(e.target.value)}
            placeholder="http://127.0.0.1:8001"
            onKeyDown={(e) => e.key === "Enter" && applyNode()}
          />
          <button onClick={applyNode}>Connect</button>
        </div>
      </header>

      <StatBar stats={stats} />

      <main className="grid">
        <section className="col services-col">
          <div className="col-head">
            <h2>Marketplace Services</h2>
            <span className="muted">{services.length} registered</span>
          </div>
          <div className="services">
            {services.length === 0 ? (
              <div className="card empty">
                <p>No services registered yet.</p>
                <p className="muted">Run <code>python demo/run_demo.py</code> to register a provider agent.</p>
              </div>
            ) : (
              services.map((s) => (
                <ServiceCard
                  key={s.service_id}
                  svc={s}
                  selected={s.service_id === selected}
                  onClick={() => setSelected(s.service_id === selected ? null : s.service_id)}
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
                <div><dt>Endpoint</dt><dd><code>{selectedSvc.endpoint}</code></dd></div>
                <div><dt>Provider</dt><dd><code>{selectedSvc.provider}</code></dd></div>
                <div><dt>Price / call</dt><dd>{selectedSvc.price_per_call_cspr.toFixed(6)} CSPR</dd></div>
                <div><dt>Stake</dt><dd>{(selectedSvc.stake_amount_cspr ?? selectedSvc.staking_amount_cspr).toFixed(3)} CSPR</dd></div>
                <div><dt>Average rating</dt><dd>{selectedSvc.average_rating.toFixed(2)} / 5</dd></div>
                <div><dt>Ratings</dt><dd>{selectedSvc.total_ratings}</dd></div>
              </dl>
            </div>
          )}
        </section>
      </main>

      <footer className="footer">
        <span>PayMesh · <a href="https://x402.org" target="_blank" rel="noreferrer">x402</a> · <a href="https://casper.network" target="_blank" rel="noreferrer">Casper</a> · Odra smart contracts</span>
      </footer>
    </div>
  );
}
