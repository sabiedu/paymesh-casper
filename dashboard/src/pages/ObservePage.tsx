import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchObserveMetrics } from "../api";
import type { ObserveMetrics, ObserveSummary, PaymentRecord } from "../types";
import { useShell } from "../components/Shell";

/* ============================================================
   helpers
   ============================================================ */

function fmtCSPR(n: number): string {
  if (n === 0) return "0";
  if (n < 0.01) return n.toFixed(4);
  if (n < 1) return n.toFixed(3);
  if (n < 1000) return n.toFixed(2);
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function fmtUptime(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (d > 0) return `${d}d ${h % 24}h`;
  return `${h}h ${m % 60}m`;
}

function shortHash(h: string, head = 10, tail = 6): string {
  if (!h) return "—";
  if (h.length <= head + tail + 1) return h;
  return `${h.slice(0, head)}…${h.slice(-tail)}`;
}

function clock(ts: number): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleTimeString([], { hour12: false });
}

function timeAgo(ts: number): string {
  if (!ts) return "never";
  const diff = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function explorerContractUrl(pkgHash: string): string {
  const clean = pkgHash.replace(/^hash-/, "");
  return `https://testnet.cspr.live/contract/${clean}`;
}

function explorerDeployUrl(deployHash: string): string {
  return `https://testnet.cspr.live/deploy/${deployHash}`;
}

const BAR_COLORS = ["#7c3aed", "#ff3366", "#6366f1", "#ec4899", "#8b5cf6", "#f43f5e", "#a855f7", "#fb7185"];

function repColor(rating: number): string {
  if (rating >= 4) return "#22c55e";
  if (rating >= 3) return "#e08600";
  return "#e23b50";
}

/* ---- copyable monospace hash ---- */
function Copyable({ text, display }: { text: string; display?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    });
  };
  return (
    <code className="mono copyable" title="click to copy" onClick={copy}>
      {display ?? text}
      <span className="copy-icon">{copied ? "✓" : "⧉"}</span>
    </code>
  );
}

/* ============================================================
   metric cards
   ============================================================ */

function MetricCard({
  label,
  value,
  accent,
  icon,
  sub,
}: {
  label: string;
  value: string;
  accent: string;
  icon: string;
  sub?: string;
}) {
  return (
    <div className={`kpi kpi-${accent}`}>
      <div className="kpi-glow" />
      <div className="kpi-top">
        <span className="kpi-icon">{icon}</span>
        {sub && <span className="kpi-sub">{sub}</span>}
      </div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </div>
  );
}

/* ---- chart tooltip ---- */
function chartTooltipStyle() {
  return {
    contentStyle: {
      background: "#ffffff",
      border: "1px solid #e7e9f2",
      borderRadius: 12,
      boxShadow: "0 10px 28px rgba(20,24,70,0.10)",
      fontSize: 12,
      padding: "8px 12px",
    },
    labelStyle: { color: "#6c7187", fontWeight: 600, marginBottom: 2 },
    itemStyle: { color: "#15182a" },
  };
}

/* ============================================================
   sections
   ============================================================ */

function VolumeChart({ metrics }: { metrics: ObserveMetrics }) {
  const data = metrics.volume_timeseries.map((p) => ({
    label: p.label,
    volume: p.volume_cspr,
  }));
  return (
    <div className="panel panel-wide">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Cumulative Payment Volume</h3>
          <p className="panel-sub">Total x402 payments settled over time · live</p>
        </div>
        <span className="panel-tag purple">{metrics.summary.total_volume_cspr.toFixed(4)} CSPR</span>
      </div>
      <div className="chart-wrap chart-tall">
        {data.length <= 1 ? (
          <EmptyInline text="No payments settled yet" />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: -8 }}>
              <defs>
                <linearGradient id="volGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7c3aed" stopOpacity={0.42} />
                  <stop offset="55%" stopColor="#a855f7" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="#ff3366" stopOpacity={0.04} />
                </linearGradient>
                <linearGradient id="volLine" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#7c3aed" />
                  <stop offset="100%" stopColor="#ff3366" />
                </linearGradient>
              </defs>
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#9499b0" }} tickLine={false} axisLine={{ stroke: "#eceef6" }} minTickGap={28} />
              <YAxis tick={{ fontSize: 11, fill: "#9499b0" }} tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => `${fmtCSPR(v)}`} />
              <Tooltip {...chartTooltipStyle()} formatter={(v: number) => [`${Number(v).toFixed(4)} CSPR`, "Volume"]} />
              <Area type="monotone" dataKey="volume" stroke="url(#volLine)" strokeWidth={2.5} fill="url(#volGrad)" dot={false} activeDot={{ r: 4, fill: "#7c3aed" }} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

function RevenueByService({ metrics }: { metrics: ObserveMetrics }) {
  const rows = metrics.payments_per_service.filter((s) => s.volume_cspr > 0);
  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Revenue by Service</h3>
          <p className="panel-sub">x402 volume per service</p>
        </div>
      </div>
      <div className="chart-wrap">
        {rows.length === 0 ? (
          <EmptyInline text="No revenue yet" />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
              <XAxis type="number" tick={{ fontSize: 11, fill: "#9499b0" }} tickLine={false} axisLine={false} tickFormatter={(v: number) => `${fmtCSPR(v)}`} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "#3a3f55" }} tickLine={false} axisLine={false} width={120} />
              <Tooltip {...chartTooltipStyle()} cursor={{ fill: "rgba(124,58,237,0.05)" }} formatter={(v: number) => [`${Number(v).toFixed(4)} CSPR`, "Volume"]} />
              <Bar dataKey="volume_cspr" radius={[0, 6, 6, 0]} barSize={18}>
                {rows.map((_, i) => (
                  <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

function ReputationDonut({ metrics }: { metrics: ObserveMetrics }) {
  const rows = metrics.reputation_breakdown.filter((r) => r.ratings_count > 0);
  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Reputation Scores</h3>
          <p className="panel-sub">Avg rating per rated service · /5</p>
        </div>
      </div>
      <div className="chart-wrap radial-wrap">
        {rows.length === 0 ? (
          <EmptyInline text="No ratings yet" />
        ) : (
          <>
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                innerRadius="28%"
                outerRadius="100%"
                data={rows.map((r) => ({ name: r.name, rating: r.rating, fill: repColor(r.rating) }))}
                startAngle={90}
                endAngle={-270}
              >
                <PolarAngleAxis type="number" domain={[0, 5]} angleAxisId={0} tick={false} />
                <RadialBar background={{ fill: "#f1f2fa" }} dataKey="rating" cornerRadius={8} angleAxisId={0} />
                <Tooltip {...chartTooltipStyle()} formatter={(v: number) => [`${Number(v).toFixed(2)} / 5`, "Rating"]} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="legend">
              {rows.map((r) => (
                <div className="legend-row" key={r.service_id}>
                  <span className="legend-dot" style={{ background: repColor(r.rating) }} />
                  <span className="legend-name">{r.name}</span>
                  <span className="legend-val">{r.rating.toFixed(1)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ContractPanel({ metrics }: { metrics: ObserveMetrics }) {
  return (
    <div className="panel panel-wide">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Deployed Contracts</h3>
          <p className="panel-sub">Odra smart contracts on Casper Testnet</p>
        </div>
        <span className="panel-tag green">4 active</span>
      </div>
      <div className="contract-grid">
        {metrics.contracts.map((c) => (
          <div className="contract-card" key={c.name}>
            <div className="contract-top">
              <span className="contract-name">{c.name}</span>
              <span className="badge-pill green">
                <span className="badge-dot" /> Active
              </span>
            </div>
            <p className="contract-desc">{c.description}</p>
            <div className="contract-hash-row">
              <span className="hash-label">pkg</span>
              <a href={explorerContractUrl(c.package_hash)} target="_blank" rel="noreferrer" className="hash-link">
                <Copyable text={c.package_hash} display={shortHash(c.package_hash, 14, 8)} />
              </a>
            </div>
            <div className="contract-hash-row">
              <span className="hash-label">dep</span>
              <a href={explorerDeployUrl(c.deploy_hash)} target="_blank" rel="noreferrer" className="hash-link">
                <code className="mono">{c.deploy_hash}</code>
                <span className="ext-icon">↗</span>
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AgentTable({ metrics }: { metrics: ObserveMetrics }) {
  const [sortKey, setSortKey] = useState<"paid_cspr" | "stake_cspr" | "reputation" | "last_active">("paid_cspr");
  const rows = [...metrics.agent_registry].sort((a, b) => {
    if (sortKey === "last_active") return b.last_active - a.last_active;
    return (b[sortKey] as number) - (a[sortKey] as number);
  });
  const headers: { key: typeof sortKey; label: string }[] = [
    { key: "paid_cspr", label: "Paid / Earned" },
    { key: "stake_cspr", label: "Stake" },
    { key: "reputation", label: "Reputation" },
    { key: "last_active", label: "Last Active" },
  ];

  return (
    <div className="panel panel-wide">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Agent Registry</h3>
          <p className="panel-sub">{metrics.agent_registry.length} unique agents on the network</p>
        </div>
      </div>
      <div className="table-scroll">
        {rows.length === 0 ? (
          <EmptyInline text="No agents registered yet" />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Address</th>
                <th>Role</th>
                <th>Services</th>
                {headers.map((h) => (
                  <th key={h.key} className="sortable" onClick={() => setSortKey(h.key)}>
                    {h.label}
                    {sortKey === h.key ? <span className="sort-arrow">▾</span> : null}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.address}>
                  <td>
                    <Copyable text={a.address} display={shortHash(a.address, 12, 8)} />
                  </td>
                  <td>
                    <span className={`role-badge ${a.is_provider && a.is_consumer ? "both" : a.is_provider ? "provider" : "consumer"}`}>
                      {a.role}
                    </span>
                  </td>
                  <td className="num">{a.services_offered}</td>
                  <td className="num">{a.paid_cspr.toFixed(4)}</td>
                  <td className="num">{a.stake_cspr.toFixed(2)}</td>
                  <td className="num">
                    <Stars rating={a.reputation} />
                  </td>
                  <td className="muted-cell">{timeAgo(a.last_active)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Stars({ rating }: { rating: number }) {
  if (rating <= 0) return <span className="muted">—</span>;
  return <span className="stars">{rating.toFixed(2)} <span className="star">★</span></span>;
}

function NetworkStrip({ metrics }: { metrics: ObserveMetrics }) {
  const n = metrics.network;
  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Network Status</h3>
          <p className="panel-sub">Settlement layer connection</p>
        </div>
      </div>
      <div className="net-grid">
        <div className="net-item">
          <span className="net-label">Network</span>
          <span className="net-value">{n.network}</span>
        </div>
        <div className="net-item">
          <span className="net-label">Chain</span>
          <span className="net-value mono">{n.chain_name}</span>
        </div>
        <div className="net-item">
          <span className="net-label">Protocol</span>
          <span className="net-value mono">{n.protocol}</span>
        </div>
        <div className="net-item">
          <span className="net-label">RPC</span>
          <span className="net-value net-live">
            <span className="live-pulse" /> Connected
          </span>
        </div>
        <a className="net-item net-link" href={n.explorer_url} target="_blank" rel="noreferrer">
          <span className="net-label">Explorer</span>
          <span className="net-value">
            testnet.cspr.live <span className="ext-icon">↗</span>
          </span>
        </a>
      </div>
    </div>
  );
}

function LiveStream({ payments }: { payments: PaymentRecord[] }) {
  const latest = payments.slice(-5).reverse();
  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Live Transactions</h3>
          <p className="panel-sub">Latest settled payments</p>
        </div>
        <span className="live-pill">
          <span className="live-pulse" /> live
        </span>
      </div>
      <div className="tx-stream">
        {latest.length === 0 ? (
          <EmptyInline text="Waiting for payments…" />
        ) : (
          latest.map((p) => (
            <div className="tx-row" key={p.index}>
              <span className="tx-time">{clock(p.timestamp)}</span>
              <span className="tx-amount">{(p.amount_motes / 1e9).toFixed(4)} CSPR</span>
              <span className="tx-addr">{shortHash(p.payer, 6, 4)}</span>
              <span className="tx-arrow">→</span>
              <span className="tx-addr">{shortHash(p.provider, 6, 4)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function EmptyInline({ text }: { text: string }) {
  return (
    <div className="empty-inline">
      <span className="empty-dot" />
      {text}
    </div>
  );
}

/* ============================================================
   skeleton
   ============================================================ */

function SkeletonGrid() {
  return (
    <div className="observe">
      <div className="kpi-row">
        {Array.from({ length: 6 }).map((_, i) => (
          <div className="kpi skeleton-card" key={i}>
            <div className="skel-line w40" />
            <div className="skel-line w70 big" />
            <div className="skel-line w50" />
          </div>
        ))}
      </div>
      <div className="panel panel-wide skeleton-card chart-tall" />
      <div className="observe-row">
        <div className="panel skeleton-card" />
        <div className="panel skeleton-card" />
      </div>
    </div>
  );
}

/* ============================================================
   main
   ============================================================ */

export default function ObservePage() {
  const { payments } = useShell();
  const [metrics, setMetrics] = useState<ObserveMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const prev = useRef<ObserveSummary | null>(null);

  const load = useCallback(async () => {
    try {
      const m = await fetchObserveMetrics();
      prev.current = metrics?.summary ?? null;
      setMetrics(m);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [metrics]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const m = await fetchObserveMetrics();
        if (active) {
          setMetrics(m);
          setError(null);
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        if (active) setLoading(false);
      }
    })();
    const id = window.setInterval(load, 3000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading && !metrics) return <SkeletonGrid />;

  if ((error && !metrics) || !metrics) {
    return (
      <div className="observe">
        <div className="big-empty">
          <div className="big-empty-icon">📡</div>
          <h2>Can't reach the metrics endpoint</h2>
          <p className="muted">{error ?? "No data available."}</p>
          <p className="muted">Make sure the PayMesh node is running on :8001.</p>
        </div>
      </div>
    );
  }

  const s = metrics.summary;
  const prevSum = prev.current;
  const volDelta = prevSum ? s.total_volume_cspr - prevSum.total_volume_cspr : 0;
  const payDelta = prevSum ? s.total_payments - prevSum.total_payments : 0;

  const hasActivity = s.total_payments > 0 || s.total_services > 0;

  return (
    <div className="observe">
      <div className="observe-head">
        <div>
          <h2 className="page-title">Observability</h2>
          <p className="page-sub">Real-time analytics for the PayMesh agent marketplace</p>
        </div>
        <span className="live-pill">
          <span className="live-pulse" /> auto-refresh · 3s
        </span>
      </div>

      {/* A. KPI cards */}
      <div className="kpi-row">
        <MetricCard label="Total Volume" value={`${fmtCSPR(s.total_volume_cspr)}`} accent="purple" icon="◈" sub={`CSPR ${volDelta > 0 ? `▲ ${volDelta.toFixed(4)}` : volDelta < 0 ? `▼ ${Math.abs(volDelta).toFixed(4)}` : "—"}`} />
        <MetricCard label="Total Payments" value={s.total_payments.toLocaleString()} accent="pink" icon="⟶" sub={payDelta > 0 ? `▲ ${payDelta} new` : "—"} />
        <MetricCard label="Active Services" value={`${s.active_services}`} accent="green" icon="◆" sub={`${s.total_services} total`} />
        <MetricCard label="Avg Reputation" value={s.avg_reputation.toFixed(2)} accent="amber" icon="★" sub="out of 5.00" />
        <MetricCard label="Total Agents" value={`${s.total_agents}`} accent="indigo" icon="◍" sub="providers + consumers" />
        <MetricCard label="Network Uptime" value={fmtUptime(s.uptime_seconds)} accent="teal" icon="⏱" sub="node alive" />
      </div>

      {/* B. Volume chart (hero) */}
      <VolumeChart metrics={metrics} />

      {/* C + D */}
      <div className="observe-row">
        <RevenueByService metrics={metrics} />
        <ReputationDonut metrics={metrics} />
      </div>

      {/* E. Contracts */}
      <ContractPanel metrics={metrics} />

      {/* F. Agents */}
      <AgentTable metrics={metrics} />

      {/* G + H */}
      <div className="observe-row">
        <NetworkStrip metrics={metrics} />
        <LiveStream payments={payments} />
      </div>

      {!hasActivity && (
        <div className="observe-cta">
          <p>No marketplace activity yet.</p>
          <Link to="/demo" className="btn-grad">
            ▶ Launch a demo to generate live data
          </Link>
        </div>
      )}
    </div>
  );
}
