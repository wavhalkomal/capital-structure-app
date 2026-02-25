import React, { useEffect, useState } from "react";

type Citation = {
  label: string;
  file: string;
  kind: string;
  where: string;
  snippet: string;
  confidence?: number;
};

type SelfCheck = {
  id: string;
  status: "pass" | "warn" | "fail";
  message: string;
  delta?: number | null;
};

type SelfAssessment = {
  score: number;
  checks: SelfCheck[];
};

interface Props {
  jobId: string;
  apiBase?: string;
}

const BonusPanels: React.FC<Props> = ({ jobId, apiBase = "" }) => {
  const [citations, setCitations] = useState<Citation[]>([]);
  const [assessment, setAssessment] = useState<SelfAssessment | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const fetchBonus = async () => {
      try {
        setError(null);

        const citationsRes = await fetch(
          `${apiBase}/api/jobs/${jobId}/bonus/citations`
        );
        const assessmentRes = await fetch(
          `${apiBase}/api/jobs/${jobId}/bonus/self_assessment`
        );

        if (!citationsRes.ok)
          throw new Error(`Citations error (${citationsRes.status})`);
        if (!assessmentRes.ok)
          throw new Error(`Self-assessment error (${assessmentRes.status})`);

        const citationsData = await citationsRes.json();
        const assessmentData = await assessmentRes.json();

        setCitations(citationsData?.citations || []);
        setAssessment(assessmentData?.self_assessment || null);
      } catch (err: any) {
        setError(err.message || "Unknown error");
      }
    };

    fetchBonus();
  }, [jobId, apiBase]);

  if (!jobId) return null;

  return (
    <div style={{ marginTop: 30 }}>
      <h2 style={{ marginBottom: 15 }}>Bonus</h2>

      {error && (
        <div
          style={{
            padding: 12,
            border: "1px solid #ffb3b3",
            borderRadius: 10,
            marginBottom: 15,
            color: "#b30000",
          }}
        >
          {error}
        </div>
      )}

      {/* Self Assessment */}
      <div
        style={{
          padding: 16,
          border: "1px solid #ddd",
          borderRadius: 12,
          marginBottom: 20,
        }}
      >
        <h3>Self-Assessment</h3>

        {!assessment ? (
          <div>Loading...</div>
        ) : (
          <>
            <div style={{ fontSize: 18, marginBottom: 10 }}>
              Score: <b>{assessment.score}</b> / 100
            </div>

            <ul>
              {assessment.checks.map((check) => (
                <li key={check.id} style={{ marginBottom: 6 }}>
                  <b>[{check.status.toUpperCase()}]</b> {check.message}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {/* Citations */}
      <div
        style={{
          padding: 16,
          border: "1px solid #ddd",
          borderRadius: 12,
        }}
      >
        <h3>Citations / Sources</h3>

        {citations.length === 0 ? (
          <div>Loading...</div>
        ) : (
          citations.map((citation, index) => (
            <div
              key={index}
              style={{
                padding: 12,
                border: "1px solid #eee",
                borderRadius: 10,
                marginBottom: 12,
                background: "#fafafa",
              }}
            >
              <div style={{ fontWeight: "bold" }}>{citation.label}</div>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
                {citation.file} • {citation.kind} • {citation.where}
                {citation.confidence !== undefined &&
                  ` • confidence=${citation.confidence}`}
              </div>
              <div
                style={{
                  fontFamily:
                    "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                  fontSize: 12,
                  whiteSpace: "pre-wrap",
                }}
              >
                {citation.snippet}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default BonusPanels;