import { useEffect, useState } from "react";

export default function BonusPanels({ jobId, apiBase = "" }) {
  const [citations, setCitations] = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!jobId) return;

    async function load() {
      try {
        setErr(null);

        const cRes = await fetch(`${apiBase}/api/jobs/${jobId}/bonus/citations`);
        const aRes = await fetch(`${apiBase}/api/jobs/${jobId}/bonus/self_assessment`);

        if (!cRes.ok) throw new Error(`Citations failed (${cRes.status})`);
        if (!aRes.ok) throw new Error(`Self-assessment failed (${aRes.status})`);

        const cJson = await cRes.json();
        const aJson = await aRes.json();

        setCitations(cJson.citations || []);
        setAssessment(aJson.self_assessment || null);
      } catch (e) {
        setErr(String(e?.message || e));
      }
    }

    load();
  }, [jobId, apiBase]);

  if (!jobId) return null;

  return (
    <div style={{ marginTop: 24 }}>
      <h2>Bonus</h2>

      {err && (
        <div style={{ padding: 12, border: "1px solid #f99", borderRadius: 8, marginBottom: 16 }}>
          <b>Bonus panel error:</b> {err}
        </div>
      )}

      {/* Self Assessment */}
      <div style={{ padding: 16, border: "1px solid #ddd", borderRadius: 12, marginBottom: 16 }}>
        <h3>Self-Assessment</h3>
        {!assessment ? (
          <div>Loading…</div>
        ) : (
          <>
            <div style={{ fontSize: 18, marginBottom: 8 }}>
              Score: <b>{assessment.score}</b>/100
            </div>
            <ul>
              {assessment.checks?.map((c) => (
                <li key={c.id}>
                  <b>[{c.status.toUpperCase()}]</b> {c.message}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {/* Citations */}
      <div style={{ padding: 16, border: "1px solid #ddd", borderRadius: 12 }}>
        <h3>Citations / Sources</h3>
        {!citations ? (
          <div>Loading…</div>
        ) : citations.length === 0 ? (
          <div>No citations found.</div>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {citations.map((c, idx) => (
              <div key={idx} style={{ padding: 12, border: "1px solid #eee", borderRadius: 10 }}>
                <div style={{ fontWeight: 600 }}>{c.label}</div>
                <div style={{ fontSize: 12, opacity: 0.8 }}>
                  {c.file} • {c.kind} • {c.where} • conf={c.confidence}
                </div>
                <div style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap" }}>
                  {c.snippet}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}