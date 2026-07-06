import { useRef, useState } from "react";
import type { AgentCallResult, FlowStep, ServiceInfo } from "../types";
import { callService, rateService } from "../api";

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

// Build the animated x402 handshake sequence. We know the price up-front so
// the "Paying" step reads naturally even before settlement confirms.
function initialSteps(price: number): FlowStep[] {
  return [
    { id: "request", label: "Requesting service…", tone: "neutral", state: "pending" },
    { id: "paywall", label: "HTTP 402 Payment Required", tone: "danger", state: "pending" },
    { id: "sign", label: "Signing x402 payment…", tone: "neutral", state: "pending" },
    { id: "pay", label: `Paying ${price.toFixed(4)} CSPR…`, tone: "neutral", state: "pending" },
    { id: "settle", label: "Payment settled on Casper", tone: "success", state: "pending" },
    { id: "result", label: "Result received", tone: "success", state: "pending" },
  ];
}

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Render a single step with the right glyph + spinner. */
function StepRow({ step }: { step: FlowStep }) {
  let glyph: React.ReactNode;
  if (step.state === "active") {
    glyph = <span className="mini-spinner" aria-hidden />;
  } else if (step.state === "done") {
    glyph = step.tone === "danger" ? <span className="x">✗</span> : <span className="check">✓</span>;
  } else if (step.state === "error") {
    glyph = <span className="x">✗</span>;
  } else {
    glyph = <span className="bullet">○</span>;
  }
  return (
    <li className={`flow-step ${step.state} tone-${step.tone}`}>
      {glyph}
      <span className="flow-label">{step.label}</span>
    </li>
  );
}

/** Pretty-print the decoded service payload. Highlights known risk-score keys. */
function ResultDisplay({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data || {});
  const score = typeof data?.risk_score === "number" ? (data.risk_score as number) : null;
  const label = typeof data?.label === "string" ? (data.label as string) : null;
  return (
    <div className="result-box">
      <div className="result-head">
        <span className="result-tag">Service response</span>
        {score !== null && (
          <div className={`score-pill ${label || ""}`}>
            <span className="score-val">{score.toFixed(3)}</span>
            <span className="score-label">{label} risk</span>
          </div>
        )}
      </div>
      <dl className="result-kv">
        {entries.map(([k, v]) => (
          <div className="kv-row" key={k}>
            <dt>{k}</dt>
            <dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** Clickable 5-star rating widget shown after a successful call. */
function RatingStars({
  value,
  onPick,
  done,
  submitting,
}: {
  value: number | null;
  onPick: (n: number) => void;
  done: boolean;
  submitting: boolean;
}) {
  const [hover, setHover] = useState(0);
  const shown = hover || value || 0;
  return (
    <div className="rate-widget">
      <span className="rate-label">{done ? "Thanks for rating! 🎉" : "Rate this service:"}</span>
      <div className="rate-stars" role="radiogroup" aria-label="star rating">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={`star ${n <= shown ? "on" : ""}`}
            disabled={done || submitting}
            onMouseEnter={() => setHover(n)}
            onMouseLeave={() => setHover(0)}
            onClick={() => onPick(n)}
            aria-label={`${n} star${n > 1 ? "s" : ""}`}
          >
            ★
          </button>
        ))}
      </div>
    </div>
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

  const [running, setRunning] = useState(false);
  const [flow, setFlow] = useState<FlowStep[] | null>(null);
  const [result, setResult] = useState<AgentCallResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [walletInput, setWalletInput] = useState("");
  const [consumer, setConsumer] = useState<string>("");

  const [rating, setRating] = useState<number | null>(null);
  const [ratingDone, setRatingDone] = useState(false);
  const [ratingBusy, setRatingBusy] = useState(false);

  const timers = useRef<number[]>([]);
  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };

  const setStep = (id: string, state: FlowStep["state"]) =>
    setFlow((prev) => (prev ? prev.map((s) => (s.id === id ? { ...s, state } : s)) : prev));

  async function handleCall(e: React.MouseEvent) {
    e.stopPropagation();
    if (running) return;
    setRunning(true);
    setErrorMsg("");
    setResult(null);
    setConsumer("");
    setRating(null);
    setRatingDone(false);
    const steps = initialSteps(svc.price_per_call_cspr);
    setFlow(steps);

    try {
      setStep("request", "active");
      await delay(550);
      setStep("request", "done");

      setStep("paywall", "active");
      await delay(680);
      setStep("paywall", "done");

      // The ACTUAL x402 consumer call fires as we begin "signing".
      setStep("sign", "active");
      const inflight = callService(svc.service_id, walletInput);
      await delay(620);
      setStep("sign", "done");

      setStep("pay", "active");
      const res = await inflight;

      if (!res.success) {
        setStep("pay", "error");
        setErrorMsg(res.error || "The paid call did not settle.");
        setResult(res);
        return;
      }

      setResult(res);
      setConsumer(res.consumer);
      setStep("pay", "done");

      setStep("settle", "active");
      await delay(700);
      setStep("settle", "done");

      setStep("result", "active");
      await delay(360);
      setStep("result", "done");
    } catch (err) {
      setStep("pay", "error");
      setErrorMsg(err instanceof Error ? err.message : "Call failed.");
    } finally {
      setRunning(false);
    }
  }

  async function handleRate(stars: number) {
    if (!consumer) return;
    setRating(stars);
    setRatingBusy(true);
    try {
      await rateService(svc.service_id, {
        reviewer: consumer,
        rating: stars,
        review: "",
      });
      setRatingDone(true);
    } catch {
      // keep stars lit even if the request hiccups — UI stays positive
      setRatingDone(true);
    } finally {
      setRatingBusy(false);
    }
  }

  function handleReset(e: React.MouseEvent) {
    e.stopPropagation();
    clearTimers();
    setFlow(null);
    setResult(null);
    setErrorMsg("");
    setConsumer("");
    setRating(null);
    setRatingDone(false);
    setRunning(false);
  }

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

      {/* ---- interactive x402 controls ---- */}
      {svc.active && (
        <div className="call-zone" onClick={(e) => e.stopPropagation()}>
          {!flow && (
            <div className="call-cta">
              <input
                className="wallet-input"
                value={walletInput}
                onChange={(e) => setWalletInput(e.target.value)}
                placeholder="wallet (optional, 0x…)"
              />
              <button className="btn-call" onClick={handleCall} disabled={running}>
                ⚡ Call via x402
              </button>
            </div>
          )}

          {flow && (
            <div className="flow-panel">
              <div className="flow-panel-head">
                <span className="flow-title">x402 payment flow</span>
                <button className="btn-ghost" onClick={handleReset} disabled={running}>
                  ✕ close
                </button>
              </div>
              <ol className="flow-list">
                {flow.map((step) => (
                  <StepRow key={step.id} step={step} />
                ))}
              </ol>

              {errorMsg && <div className="flow-error">⚠ {errorMsg}</div>}

              {result && result.success && (
                <>
                  {result.data && <ResultDisplay data={result.data} />}
                  <div className="settle-meta">
                    <div>
                      <span className="kv-k">Paid</span>
                      <span className="kv-v">{result.amount_paid_cspr} CSPR</span>
                    </div>
                    <div>
                      <span className="kv-k">Settlement</span>
                      <span className="kv-v mono">{result.settlement_id ? short(result.settlement_id, 16) : "—"}</span>
                    </div>
                    <div>
                      <span className="kv-k">Consumer</span>
                      <span className="kv-v mono">{short(result.consumer, 14)}</span>
                    </div>
                  </div>
                  {consumer && (
                    <RatingStars
                      value={rating}
                      onPick={handleRate}
                      done={ratingDone}
                      submitting={ratingBusy}
                    />
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
