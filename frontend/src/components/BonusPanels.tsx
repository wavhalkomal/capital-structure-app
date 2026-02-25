import React, { useEffect, useMemo, useState } from "react";

type Props = {
  jobId: string;
  apiBase: string; // "" for same-origin, or "https://your-domain"
};

type AnyObj = Record<string, any>;

function joinBase(base: string, path: string) {
  const b = (base || "").replace(/\/+$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${b}${p}`;
}

export default function BonusPanels({ jobId, apiBase }: Props) {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<AnyObj | null>(null);

  const url = useMemo(() => {
    if (!jobId) return null;
    return joinBase(apiBase, `/api/jobs/${jobId}/result`);
  }, [apiBase, jobId]);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!url) {
        setResult(null);
        setErr(null);
        return;
      }
      setLoading(true);
      setErr(null);

      try {
        const r = await fetch(url, { method: "GET" });
        if (!r.ok) {
          const txt = await r.text().catch(() => "");
          throw new Error(`Failed to load result (${r.status}). ${txt}`.trim());
        }
        const data = (await r.json()) as AnyObj;
        if (!cancelled) setResult(data);
      } catch (e: any) {
        if (!cancelled) setErr(e?.message || "Failed to load bonus info");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    run();
    // refresh every 2s while job is running (safe even if job already finished)
    const t = setInterval(run, 2000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [url]);

  // These keys are OPTIONAL — component won’t crash if you haven’t added them yet.
  const citations = result?.citations ?? result?.bonus?.citations ?? null;
  const selfAssessment =
    result?.self_assessment ?? result?.bonus?.self_assessment ?? null;

  if (!jobId) return null;

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 8 }}>
        Bonus: Citations & Self-Assessment
      </div>

      {loading && (
        <div style={{ opacity: 0.7, fontSize: 13 }}>Loading bonus info…</div>
      )}

      {err && (
        <div style={{ color: "#b00020", fontSize: 13 }}>
          {err}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          marginTop: 8,
        }}
      >
        {/* Citations */}
        <div style={{ border: "1px solid #ddd", borderRadius: 10, padding: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Citations</div>

          {!citations && (
            <div style={{ fontSize: 13, opacity: 0.75 }}>
              Not available yet. (Backend must include <code>citations</code> in the job result.)
            </div>
          )}

          {citations && (
            <pre
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: 12,
                margin: 0,
              }}
            >
              {JSON.stringify(citations, null, 2)}
            </pre>
          )}
        </div>

        {/* Self-Assessment */}
        <div style={{ border: "1px solid #ddd", borderRadius: 10, padding: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Self-Assessment</div>

          {!selfAssessment && (
            <div style={{ fontSize: 13, opacity: 0.75 }}>
              Not available yet. (Backend must include <code>self_assessment</code> in the job result.)
            </div>
          )}

          {selfAssessment && (
            <pre
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: 12,
                margin: 0,
              }}
            >
              {JSON.stringify(selfAssessment, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
