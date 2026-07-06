import { useEffect, useState } from "react";
import { registerService, stakeService } from "../api";

/** Generate a plausible random Casper-ish public-key hex (32 bytes). */
function randomProviderHex(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return "0x" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Slugify a service name into a registry id: "DeFi Risk API" → "defi-risk-api". */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

export interface ListResult {
  serviceId: string;
  provider: string;
}

export default function ListServiceModal({
  onClose,
  onSubmitted,
}: {
  onClose: () => void;
  onSubmitted: (res: ListResult) => Promise<void> | void;
}) {
  const [name, setName] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [price, setPrice] = useState("0.05");
  const [stake, setStake] = useState("5.0");
  const [description, setDescription] = useState("");
  const [endpointOverride, setEndpointOverride] = useState("");
  const [touchedId, setTouchedId] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>("");

  // Auto-generate the service id from the name until the user edits it.
  useEffect(() => {
    if (!touchedId) setServiceId(slugify(name));
  }, [name, touchedId]);

  const derivedEndpoint = `http://127.0.0.1:8002/${serviceId || "service"}`;
  const endpoint = endpointOverride.trim() || derivedEndpoint;

  const priceNum = parseFloat(price);
  const stakeNum = parseFloat(stake);
  const valid =
    name.trim().length > 1 &&
    serviceId.trim().length > 1 &&
    Number.isFinite(priceNum) &&
    priceNum > 0 &&
    Number.isFinite(stakeNum) &&
    stakeNum > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || submitting) return;
    setSubmitting(true);
    setError("");
    const provider = randomProviderHex();
    try {
      await registerService({
        provider,
        service_id: serviceId.trim(),
        name: name.trim(),
        endpoint,
        price_per_call_cspr: priceNum,
        staking_amount_cspr: stakeNum,
        ...(description.trim() ? { description: description.trim() } : {}),
      });
      await stakeService(serviceId.trim(), { provider, amount_cspr: stakeNum });
      await onSubmitted({ serviceId: serviceId.trim(), provider });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to list service.");
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal-head">
          <div>
            <h2>Deploy a new AI agent</h2>
            <p className="modal-sub">List a paid service on the PayMesh marketplace. It becomes callable via x402 instantly.</p>
          </div>
          <button className="btn-ghost" onClick={onClose} aria-label="close">✕</button>
        </div>

        <form className="modal-form" onSubmit={handleSubmit}>
          <label className="field">
            <span className="field-label">Service name</span>
            <input
              className="field-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="DeFi Wallet Risk Score API"
              autoFocus
            />
          </label>

          <div className="field-row">
            <label className="field">
              <span className="field-label">Service ID</span>
              <input
                className="field-input mono"
                value={serviceId}
                onChange={(e) => {
                  setTouchedId(true);
                  setServiceId(e.target.value);
                }}
                placeholder="risk-score-api"
              />
            </label>
            <label className="field">
              <span className="field-label">Endpoint</span>
              <input
                className="field-input mono"
                value={endpointOverride}
                onChange={(e) => setEndpointOverride(e.target.value)}
                placeholder={derivedEndpoint}
              />
            </label>
          </div>

          <div className="field-row">
            <label className="field">
              <span className="field-label">Price / call (CSPR)</span>
              <input
                className="field-input"
                type="number"
                min="0"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">Stake (CSPR)</span>
              <input
                className="field-input"
                type="number"
                min="0"
                step="0.5"
                value={stake}
                onChange={(e) => setStake(e.target.value)}
              />
            </label>
          </div>

          <label className="field">
            <span className="field-label">Description (optional)</span>
            <textarea
              className="field-input"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What does this agent do?"
            />
          </label>

          <div className="modal-hint">
            <span className="kv-k">Provider key</span>
            <code className="muted">auto-generated client-side · Casper Ed25519-style</code>
          </div>

          {error && <div className="modal-error">⚠ {error}</div>}

          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="btn-grad" disabled={!valid || submitting}>
              {submitting ? "Deploying…" : "⚡ Deploy & stake"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
