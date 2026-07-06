import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketplaceStats, PaymentRecord, ServiceInfo } from "./types";
import {
  checkHealth,
  fetchRecentPayments,
  fetchServices,
  fetchStats,
} from "./api";
import ServiceCard from "./components/ServiceCard";
import TransactionFeed from "./components/TransactionFeed";
import ListServiceModal, { type ListResult } from "./components/ListServiceModal";
import DemoConsole from "./components/DemoConsole";

function usePulse<T>(value: T): boolean {
  const prev = useRef<T>(value);
  const [pulse, setPulse] = useState(false);
  useEffect(() => {
    if (prev.current !== value) {
      prev.current = value;
      setPulse(true);
      const t = window.setTimeout(() => setPulse(false), 750);
      return () => window.clearTimeout(t);
    }
  }, [value]);
  return pulse;
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  const pulse = usePulse(value);
  return (
    <div className={`stat ${pulse ? "pulse" : ""}`} key={label}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

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

interface Toast {
  id: number;
  text: string;
  tone: "success" | "error";
}

export default function App() {
  const [stats, setStats] = useState<MarketplaceStats | null>(null);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [online, setOnline] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const pushToast = useCallback((text: string, tone: Toast["tone"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, text, tone }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4200);
  }, []);

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

  const selectedSvc = services.find((s) => s.service_id === selected) || null;

  const handleListed = useCallback(
    async (res: ListResult) => {
      setModalOpen(false);
      pushToast(`✓ ${res.serviceId} deployed & staked`);
      await refresh();
      // surface the new card
      setSelected(res.serviceId);
    },
    [refresh, pushToast]
  );

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
          <span className={`status ${online ? "ok" : "down"}`}>
            ● {online ? "node online" : "node offline"}
          </span>
          <button className="btn-grad" onClick={() => setModalOpen(true)}>
            + List a Service
          </button>
        </div>
      </header>

      <StatBar stats={stats} />

      <DemoConsole services={services} onAfterAction={refresh} />

      <main className="grid">
        <section className="col services-col">
          <div className="col-head">
            <h2>Marketplace Services</h2>
            <span className="muted">
              {services.length} registered · click a card, then <strong>Call via x402</strong>
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
                    <code>{selectedSvc.endpoint}</code>
                  </dd>
                </div>
                <div>
                  <dt>Provider</dt>
                  <dd>
                    <code>{selectedSvc.provider}</code>
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

      {modalOpen && (
        <ListServiceModal
          onClose={() => setModalOpen(false)}
          onSubmitted={handleListed}
        />
      )}

      {/* toast stack */}
      <div className="toast-stack">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.tone}`}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}
