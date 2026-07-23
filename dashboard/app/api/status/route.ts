import { NextResponse } from "next/server";

// Proxies the real backend (webhook_handler.py's GET /jobs/latest) and
// reshapes its Job Store row into the flat shape the dashboard UI expects.
// Never throws to the client: backend-down and no-jobs-yet are both valid,
// distinguishable states, not exceptions.

type BackendStatus =
  | "RECEIVED"
  | "QUEUED"
  | "FETCHING_CONTEXT"
  | "ANALYZING"
  | "VALIDATING"
  | "POSTING_TO_GITHUB"
  | "COMPLETED"
  | "FAILED";

interface BackendFinding {
  rule_id: string;
  severity: "critical" | "high" | "medium" | "low";
  path: string;
  line: number;
  message: string;
  suggestion: string | null;
}

interface BackendJob {
  id: number;
  repo_full_name: string;
  pr_number: number;
  pr_title: string | null;
  pr_author: string | null;
  status: BackendStatus;
  error: string | null;
  updated_at: string;
}

interface BackendLatestJobResponse {
  job: BackendJob | null;
  findings: BackendFinding[];
}

const TERMINAL_TO_UI_STATUS: Record<string, "completed" | "failed"> = {
  COMPLETED: "completed",
  FAILED: "failed",
};

function toUiStatus(status: BackendStatus): "analyzing" | "completed" | "failed" {
  return TERMINAL_TO_UI_STATUS[status] ?? "analyzing";
}

// Deterministic, UI-only summary score — the backend doesn't persist one.
function scoreFrom(counts: { critical: number; high: number; medium: number; low: number }): number {
  const penalty = counts.critical * 3 + counts.high * 2 + counts.medium * 1 + counts.low * 0.5;
  return Math.max(0, Math.min(10, Math.round(10 - penalty)));
}

export async function GET() {
  const backendUrl = process.env.WEBHOOK_API_URL ?? "http://localhost:8000";

  let payload: BackendLatestJobResponse;
  try {
    const res = await fetch(`${backendUrl}/jobs/latest`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      throw new Error(`backend responded ${res.status}`);
    }
    payload = await res.json();
  } catch (error) {
    return NextResponse.json({
      state: "error" as const,
      message:
        "No se pudo conectar con el backend. Verifica que el Webhook Handler esté corriendo (docker compose up -d).",
      detail: error instanceof Error ? error.message : String(error),
    });
  }

  if (payload.job === null) {
    return NextResponse.json({ state: "empty" as const });
  }

  const { job, findings } = payload;
  const counts = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const f of findings) {
    counts[f.severity] += 1;
  }

  return NextResponse.json({
    state: "ok" as const,
    data: {
      pr: {
        number: job.pr_number,
        title: job.pr_title ?? `Pull Request #${job.pr_number}`,
        author: job.pr_author ?? "unknown",
        repo: job.repo_full_name,
        status: toUiStatus(job.status),
      },
      findings: findings.map((f) => ({
        file: f.path,
        line: f.line,
        severity: f.severity,
        category: f.rule_id,
        issue: f.message,
        suggestion: f.suggestion ?? "",
      })),
      summary: {
        total: findings.length,
        ...counts,
        score: scoreFrom(counts),
      },
    },
  });
}
