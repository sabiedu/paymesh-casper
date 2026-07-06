import { useCallback, useEffect, useRef, useState } from "react";
import { Outlet, NavLink, useOutletContext } from "react-router-dom";
import type { MarketplaceStats, PaymentRecord, ServiceInfo } from "../types";
import { checkHealth, fetchRecentPayments, fetchServices, fetchStats } from "../api";
import ListServiceModal, { type ListResult } from "./ListServiceModal";

/** Shared marketplace state handed to every routed page via the Shell layout. */
export interface ShellContext {
  stats: MarketplaceStats | null;
  services: ServiceInfo[];
  payments: PaymentRecord[];
  online: boolean;
  refresh: () => Promise<void>;
  pushToast: (text: string, tone?: ToastTone) => void;
  openListModal: () => void;
}

export type ToastTone = "success" | "error";

export function useShell(): ShellContext {
  return useOutletContext<ShellContext>();
}

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

export function Stat({
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

interface Toast {
  id: number;
  text: string;
  tone: ToastTone;
}

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/observe", label: "Observe" },
  { to: "/demo", label: "Demo" },
];

export default function Shell() {
  const [stats, setStats] = useState<MarketplaceStats | null>(null);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [online, setOnline] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const pushToast = useCallback((text: string, tone: ToastTone = "success") => {
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

  const openListModal = useCallback(() => setModalOpen(true), []);

  const handleListed = useCallback(
    async (res: ListResult) => {
      setModalOpen(false);
      pushToast(`✓ ${res.serviceId} deployed & staked`);
      await refresh();
    },
    [refresh, pushToast]
  );

  const ctx: ShellContext = {
    stats,
    services,
    payments,
    online,
    refresh,
    pushToast,
    openListModal,
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◆</span>
          <div>
            <h1>
              PayMesh{" "}
              <span className={`live-badge ${online ? "on" : "off"}`}>
                <span className="live-dot" /> {online ? "LIVE" : "OFFLINE"}
              </span>
            </h1>
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

      <nav className="navbar">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `nav-link ${isActive ? "active" : ""}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <Outlet context={ctx} />

      {modalOpen && <ListServiceModal onSubmitted={handleListed} onClose={() => setModalOpen(false)} />}

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
