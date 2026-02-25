import React, { useMemo, useState } from "react";
import BonusPanels from "./components/BonusPanels";

type JobStatus = "queued" | "running" | "succeeded" | "failed";

type JobInfo = {
  job_id: string;
  status: JobStatus;
  error?: string | null;
  ticker?: string | null;
  market_cap_mm?: number | null;
  market_cap_meta?: any;
};

type ResultPayload = {
  job_id: string;
  html: string;
  built: any;
  ticker?: string | null;
  market_cap_mm?: number | null;
  market_cap_meta?: any;
};

const API_BASE = import.meta.env.VITE_API_BASE || "";

function Button(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { style, ...rest } = props;
  return (
    <button
      {...rest}
      style={{
        padding: "10px 12px",
        borderRadius: 12,
        border: "1px solid #ddd",
        background: "white",
        cursor: props.disabled ? "not-allowed" : "pointer",
        ...style,
      }}
    />
  );
}

function FileField(props: { label: string; accept: string; onChange: (f: File | null) => void }) {
  return (
    <div>
      <label style={{ fontSize: 13, color: "#444" }}>{props.label}</label>
      <input
        type="file"
        accept={props.accept}
        onChange={(e) => props.onChange(e.target.files?.[0] || null)}
        style={{ display: "block", marginTop: 6 }}
      />
    </div>
  );
}

export default function App() {
  const [balanceSheet, setBalanceSheet] = useState<File | null>(null);
  const [debtNote, setDebtNote] = useState<File | null>(null);
  const [leaseNote, setLeaseNote] = useState<File | null>(null);
  const [metadata, setMetadata] = useState<File | null>(null);

  const [ticker, setTicker] = useState<string>("");
  const [marketCap, setMarketCap] = useState<string>("");

  const [job, setJob] = useState<JobInfo | null>(null);
  const [result, setResult] = useState<ResultPayload | null>(null);

  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>("");

  const jobId = job?.job_id || "";

  const canSubmit = useMemo(() => {
    return !!balanceSheet && !!debtNote && !!leaseNote && !!metadata && !busy;
  }, [balanceSheet, debtNote, leaseNote, metadata, busy]);

  async function createJob() {
    if (!balanceSheet || !debtNote || !leaseNote || !metadata) {
      setMsg("Please upload all 4 required files.");
      return;
    }

    setBusy(true);
    setMsg("");
    setJob(null);
    setResult(null);

    try {
      const fd = new FormData();
      fd.append("balance_sheet", balanceSheet);
      fd.append("debt_note", debtNote);
      fd.append("lease_note", leaseNote);
      fd.append("metadata", metadata);

      const t = ticker.trim();
      if (t) fd.append("ticker", t);

      const mc = marketCap.trim();
      if (mc) fd.append("market_cap_mm", mc);

      const res = await fetch(`${API_BASE}/api/jobs`, {
        method: "POST",
        body: fd,
      });

      const body = await res.json().catch(() => ({}));

      if (!res.ok) {
        setBusy(false);
        setMsg(body?.detail ? String(body.detail) : `Failed creating job (${res.status})`);
        return;
      }

      setJob(body as JobInfo);
      setMsg("Job created. Processing…");
      pollJob(body.job_id);
    } catch (e: any) {
      setMsg(e?.message || String(e));
      setBusy(false);
    }
  }

  async function pollJob(jid: string) {
    try {
      while (true) {
        const jr = await fetch(`${API_BASE}/api/jobs/${jid}`);
        const jb = await jr.json().catch(() => null);

        if (!jr.ok || !jb) {
          setMsg(`Failed fetching job status (${jr.status})`);
          setBusy(false);
          return;
        }

        setJob(jb);

        if (jb.status === "failed") {
          setMsg(jb.error || "Job failed.");
          setBusy(false);
          return;
        }

        if (jb.status === "succeeded") {
          setMsg("Job succeeded.");
          await fetchResult(jid);
          setBusy(false);
          return;
        }

        await new Promise((r) => setTimeout(r, 1200));
      }
    } catch (e: any) {
      setMsg(e?.message || String(e));
      setBusy(false);
    }
  }

  async function fetchResult(jid: string) {
    const rr = await fetch(`${API_BASE}/api/jobs/${jid}/result`);
    const rb = await rr.json().catch(() => null);

    if (!rr.ok || !rb) {
      setMsg(`Failed fetching result (${rr.status})`);
      return;
    }

    // Your backend returns JSON; html content is in rb.html based on your app
    setResult(rb as ResultPayload);
  }

  const htmlDownloadUrl = jobId ? `${API_BASE}/api/jobs/${jobId}/download/html` : "";
  const jsonDownloadUrl = jobId ? `${API_BASE}/api/jobs/${jobId}/download/json` : "";

  return (
    <div style={{ maxWidth: 980, margin: "28px auto", padding: "0 16px", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto" }}>
      <h1 style={{ marginBottom: 6 }}>Capital Structure Extractor</h1>
      <div style={{ color: "#666", marginBottom: 18 }}>
        Upload inputs → build → render HTML output.
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div style={{ padding: 16, border: "1px solid #ddd", borderRadius: 14 }}>
          <h3 style={{ marginTop: 0 }}>Inputs</h3>

          <div style={{ display: "grid", gap: 12 }}>
            <FileField label="Balance Sheet (balance_sheet.json)" accept=".json" onChange={setBalanceSheet} />
            <FileField label="Debt Note (debt_note.html)" accept=".html,.htm" onChange={setDebtNote} />
            <FileField label="Lease Note (lease_note.html)" accept=".html,.htm" onChange={setLeaseNote} />
            <FileField label="Metadata (metadata.json)" accept=".json" onChange={setMetadata} />
          </div>

          <div style={{ marginTop: 14, display: "grid", gap: 10 }}>
            <div>
              <label style={{ fontSize: 13, color: "#444" }}>Ticker (optional)</label>
              <input
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                placeholder="AAP"
                style={{ width: "100%", marginTop: 6, padding: 10, borderRadius: 12, border: "1px solid #ddd" }}
              />
            </div>

            <div>
              <label style={{ fontSize: 13, color: "#444" }}>Market Cap ($mm) (optional override)</label>
              <input
                value={marketCap}
                onChange={(e) => setMarketCap(e.target.value)}
                placeholder="2592"
                style={{ width: "100%", marginTop: 6, padding: 10, borderRadius: 12, border: "1px solid #ddd" }}
              />
            </div>
          </div>

          <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
            <Button onClick={createJob} disabled={!canSubmit}>
              {busy ? "Working…" : "Run"}
            </Button>

            <Button
              onClick={() => {
                setBalanceSheet(null);
                setDebtNote(null);
                setLeaseNote(null);
                setMetadata(null);
                setTicker("");
                setMarketCap("");
                setJob(null);
                setResult(null);
                setMsg("");
              }}
              disabled={busy}
            >
              Reset
            </Button>
          </div>

          {msg && <div style={{ marginTop: 12, color: "#333" }}>{msg}</div>}
        </div>

        <div style={{ padding: 16, border: "1px solid #ddd", borderRadius: 14 }}>
          <h3 style={{ marginTop: 0 }}>Job</h3>

          {!job ? (
            <div style={{ color: "#666" }}>No job yet.</div>
          ) : (
            <div style={{ display: "grid", gap: 8 }}>
              <div>
                <b>ID:</b> <code>{job.job_id}</code>
              </div>
              <div>
                <b>Status:</b> {job.status}
              </div>
              {job.error ? (
                <div style={{ color: "#b00" }}>
                  <b>Error:</b> {job.error}
                </div>
              ) : null}

              <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
                <Button disabled={!jobId || job.status !== "succeeded"} onClick={() => window.open(htmlDownloadUrl, "_blank")}>
                  Download HTML
                </Button>
                <Button disabled={!jobId || job.status !== "succeeded"} onClick={() => window.open(jsonDownloadUrl, "_blank")}>
                  Download JSON
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      <section style={{ marginTop: 16, padding: 16, border: "1px solid #ddd", borderRadius: 14 }}>
        <h3 style={{ marginTop: 0 }}>Output</h3>

        {!result?.html ? (
          <div style={{ color: "#666" }}>Rendered capital structure HTML will appear here.</div>
        ) : (
          <>
            <div style={{ marginTop: 12 }}>
              <iframe
                title="Capital Structure Output"
                style={{ width: "100%", height: 720, border: "1px solid #ddd", borderRadius: 12, background: "white" }}
                srcDoc={result.html}
              />
            </div>

            {/* ✅ BONUS PANELS AT THE END */}
            <BonusPanels jobId={job?.job_id || ""} apiBase={API_BASE} />
          </>
        )}
      </section>

      <footer style={{ marginTop: 18, color: "#666", fontSize: 12 }}>
        API: <code>{API_BASE || "(same origin)"}</code>
      </footer>
    </div>
  );
}