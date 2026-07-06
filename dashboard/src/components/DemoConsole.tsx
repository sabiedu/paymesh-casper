import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import type { ServiceInfo } from "../types";
import type { DemoActivityEvent } from "../api";
import {
  demoConsumerCall,
  demoRegisterProvider,
  demoRunFullFlow,
  fetchActivity,
} from "../api";

type BusyKey = "register" | "consumer" | "flow";

// Per-event-type styling (badge label + accent color) for the activity log.
const TYPE_STYLE: Record<
  DemoActivityEvent["type"] | "default",
  { label: string; color: string }
> = {
  provider: { label: "PROVIDER", color: "#7c3aed" },
  discover: { label: "DISCOVER", color: "#4f46e5" },
  consumer: { label: "CONSUMER", color: "#2563eb" },
  payment: { label: "x402", color: "#0891b2" },
  settlement: { label: "SETTLED", color: "#15a34a" },
  rating: { label: "RATING", color: "#d97706" },
  system: { label: "SYSTEM", color: "#6c7187" },
  default: { label: "EVENT", color: "#6c7187" },
};

function clock(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour12: false });
}

export default function DemoConsole({
  services,
  onAfterAction,
}: {
  services: ServiceInfo[];
  onAfterAction: () => void;
}) {
  const [events, setEvents] = useState<DemoActivityEvent[]>([]);
  const [busy, setBusy] = useState<Record<BusyKey, boolean>>({
    register: false,
    consumer: false,
    flow: false,
  });
  const [payAnim, setPayAnim] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flowResult, setFlowResult] = useState<string | null>(null);

  const lastIdRef = useRef(0);
  const feedRef = useRef<HTMLDivElement | null>(null);
  const stickRef = useRef(true);

  // Track whether the user is scrolled to the bottom (for auto-scroll).
  const onFeedScroll = useCallback(() => {
    const el = feedRef.current;
    if (!el) return;
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }, []);

  // Poll the activity log. Poll faster while a demo action is running so the
  // stream visibly animates in as steps complete.
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const evs = await fetchActivity(0);
        if (!active) return;
        const maxId = evs.length ? evs[evs.length - 1].id : lastIdRef.current;
        lastIdRef.current = Math.max(lastIdRef.current, maxId);
        setEvents(evs.slice(-120));
      } catch {
        /* node may be mid-restart; ignore */
      } finally {
        const fast = busy.register || busy.consumer || busy.flow;
        timer = setTimeout(poll, fast ? 450 : 1500);
      }
    };
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [busy.register, busy.consumer, busy.flow]);

  // Auto-scroll the feed to the bottom when new events arrive (if stuck).
  useEffect(() => {
    const el = feedRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [events]);

  const flashPayment = useCallback(() => {
    setPayAnim(true);
    setTimeout(() => setPayAnim(false), 2600);
  }, []);

  const handleRegister = useCallback(async () => {
    setError(null);
    setFlowResult(null);
    setBusy((b) => ({ ...b, register: true }));
    try {
      const svc = await demoRegisterProvider();
      setError(null);
      void svc;
      onAfterAction();
    } catch (e) {
      setError(`Register failed: ${(e as Error).message}`);
    } finally {
      setBusy((b) => ({ ...b, register: false }));
      onAfterAction();
    }
  }, [onAfterAction]);

  const pickTarget = useCallback((): ServiceInfo | null => {
    const active = services.filter((s) => s.active);
    if (!active.length) return null;
    // Prefer demo-registered services (served via /serve/ — always callable),
    // then the seeded risk-score-api (served by the provider process). This
    // avoids targeting services registered via the manual List-a-Service flow
    // whose provider endpoints may not be live yet.
    const demo = active.filter((s) => s.endpoint.includes("/serve/"));
    if (demo.length) return demo[demo.length - 1];
    const seeded = active.find((s) => s.service_id === "risk-score-api");
    if (seeded) return seeded;
    return active[active.length - 1];
  }, [services]);

  const handleConsumer = useCallback(async () => {
    setError(null);
    setFlowResult(null);
    const target = pickTarget();
    if (!target) {
      setError("No active service to call. Register a provider agent first.");
      return;
    }
    setBusy((b) => ({ ...b, consumer: true }));
    flashPayment();
    try {
      const res = await demoConsumerCall(target.service_id);
      if (!res.success) {
        setError(`Consumer call did not settle: ${res.error ?? "unknown"}`);
      }
      onAfterAction();
    } catch (e) {
      setError(`Consumer call failed: ${(e as Error).message}`);
    } finally {
      setBusy((b) => ({ ...b, consumer: false }));
      onAfterAction();
    }
  }, [pickTarget, flashPayment, onAfterAction]);

  const handleFlow = useCallback(async () => {
    setError(null);
    setFlowResult(null);
    setBusy((b) => ({ ...b, flow: true }));
    flashPayment();
    try {
      const res = await demoRunFullFlow();
      setFlowResult(
        `✅ ${res.service.emoji} ${res.service.name} — ${res.calls.length} paid calls, ` +
          `${res.total_volume_cspr.toFixed(4)} CSPR settled via x402`,
      );
      onAfterAction();
    } catch (e) {
      setError(`Full flow failed: ${(e as Error).message}`);
    } finally {
      setBusy((b) => ({ ...b, flow: false }));
      onAfterAction();
    }
  }, [flashPayment, onAfterAction]);

  const anyBusy = busy.register || busy.consumer || busy.flow;
  const target = pickTarget();

  return (
    <section className="demo-console">
      <div className="demo-head">
        <div>
          <h2>⚡ Live Demo Console</h2>
          <p className="demo-sub">
            One-click agent lifecycle — real x402 payments settling on Casper, right here.
          </p>
        </div>
        <span className={`demo-pill ${anyBusy ? "running" : "idle"}`}>
          <span className="pulse-dot" /> {anyBusy ? "agents running…" : "ready"}
        </span>
      </div>

      <div className="demo-controls">
        <button
          className={`demo-btn purple ${busy.register ? "loading" : ""}`}
          onClick={handleRegister}
          disabled={anyBusy}
        >
          <span className="demo-btn-ico">🟣</span>
          <span className="demo-btn-txt">
            <strong>Register Provider Agent</strong>
            <small>generate identity · register · stake</small>
          </span>
        </button>

        <button
          className={`demo-btn blue ${busy.consumer ? "loading" : ""}`}
          onClick={handleConsumer}
          disabled={anyBusy}
        >
          <span className="demo-btn-ico">🔵</span>
          <span className="demo-btn-txt">
            <strong>Launch Consumer Agent</strong>
            <small>
              {target ? `call ${target.service_id.slice(0, 22)}…` : "register a provider first"}
            </small>
          </span>
        </button>

        <button
          className={`demo-btn green ${busy.flow ? "loading" : ""}`}
          onClick={handleFlow}
          disabled={anyBusy}
        >
          <span className="demo-btn-ico">🟢</span>
          <span className="demo-btn-txt">
            <strong>Run Full Demo Flow</strong>
            <small>register → 4 paid calls → rate</small>
          </span>
        </button>
      </div>

      {/* x402 payment flow visualization */}
      <div className={`pay-flow ${payAnim ? "active" : ""}`} aria-hidden={!payAnim}>
        <div className="pay-node consumer">
          <span>Consumer</span>
          <small>Agent</small>
        </div>
        <div className="pay-wire">
          <span className="pay-label">x402 · 0.05 CSPR</span>
          <span className="pay-dot" />
        </div>
        <div className="pay-node provider">
          <span>Provider</span>
          <small>Agent</small>
        </div>
        <div className="pay-wire settle">
          <span className="pay-label">settle</span>
          <span className="pay-dot" />
        </div>
        <div className="pay-node chain">
          <span>◈ Casper</span>
          <small>Settlement</small>
        </div>
      </div>

      {flowResult && <div className="demo-flash success">{flowResult}</div>}
      {error && <div className="demo-flash error">{error}</div>}

      {/* live activity log */}
      <div className="activity-card">
        <div className="activity-head">
          <h3>📟 Agent Activity Log</h3>
          <span className="activity-count">{events.length} events</span>
        </div>
        <div className="activity-feed" ref={feedRef} onScroll={onFeedScroll}>
          {events.length === 0 ? (
            <div className="activity-empty">
              <p>No activity yet.</p>
              <p className="muted">
                Click <em>Register Provider Agent</em> or <em>Run Full Demo Flow</em> to watch the
                marketplace come alive.
              </p>
            </div>
          ) : (
            events.map((e) => {
              const st = TYPE_STYLE[e.type] ?? TYPE_STYLE.default;
              return (
                <div
                  className="activity-row"
                  key={e.id}
                  style={{ "--accent": st.color } as CSSProperties}
                >
                  <span className="activity-ts">{clock(e.ts)}</span>
                  <span className="activity-icon">{e.icon}</span>
                  <span className="activity-badge">{st.label}</span>
                  <span className="activity-msg">{e.message}</span>
                </div>
              );
            })
          )}
        </div>
      </div>
    </section>
  );
}
