"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { PRCard, PRStatus } from "@/components/PRCard";
import { CommentPreview, Severity } from "@/components/CommentPreview";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Shield, Activity, AlertTriangle, Inbox, RefreshCw } from "lucide-react";

interface Finding {
  file: string;
  line: number;
  severity: Severity;
  category: string;
  issue: string;
  suggestion: string;
}

interface PRData {
  number: number;
  title: string;
  author: string;
  repo: string;
  status: PRStatus;
}

interface AnalysisResult {
  pr: PRData;
  findings: Finding[];
  summary: {
    total: number;
    critical: number;
    high: number;
    medium: number;
    low: number;
    score: number;
  };
}

type StatusResponse =
  | { state: "ok"; data: AnalysisResult }
  | { state: "empty" }
  | { state: "error"; message: string };

const POLL_INTERVAL_MS = 5000;

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/status", { cache: "no-store" });
      const data: StatusResponse = await res.json();
      setStatus(data);
    } catch {
      setStatus({ state: "error", message: "No se pudo contactar al dashboard." });
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load, then poll every 5s only while the latest job is still
  // being analyzed — no point polling a completed/failed/empty result.
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    const isAnalyzing = status?.state === "ok" && status.data.pr.status === "analyzing";

    if (isAnalyzing && pollRef.current === null) {
      pollRef.current = setInterval(fetchStatus, POLL_INTERVAL_MS);
    }
    if (!isAnalyzing && pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    return () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [status, fetchStatus]);

  const result = status?.state === "ok" ? status.data : null;

  return (
    <main className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b bg-background/80 backdrop-blur-sm">
        <div className="container mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Shield className="h-5 w-5 text-primary" />
            <span className="font-bold text-lg tracking-tight">PR Guardian</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground font-mono hidden sm:block">
              groq/llama-3.3-70b
            </span>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="container mx-auto px-6 py-10 max-w-2xl">
        {/* Initial load */}
        {loading && (
          <div className="flex flex-col items-center gap-4 py-20">
            <div className="relative">
              <div className="h-12 w-12 rounded-full border-2 border-muted" />
              <div className="absolute inset-0 h-12 w-12 rounded-full border-2 border-t-primary animate-spin" />
            </div>
            <p className="text-sm text-muted-foreground">Conectando con el backend...</p>
          </div>
        )}

        {/* Backend unreachable */}
        {!loading && status?.state === "error" && (
          <div className="flex flex-col items-center text-center gap-4 py-16">
            <div className="h-16 w-16 rounded-2xl bg-destructive/10 flex items-center justify-center">
              <AlertTriangle className="h-8 w-8 text-destructive" />
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-bold tracking-tight">Backend no disponible</h2>
              <p className="text-muted-foreground text-sm max-w-md">{status.message}</p>
            </div>
            <Button onClick={fetchStatus} variant="outline" size="sm" className="gap-2 mt-2">
              <RefreshCw className="h-3.5 w-3.5" />
              Reintentar
            </Button>
          </div>
        )}

        {/* No jobs yet */}
        {!loading && status?.state === "empty" && (
          <div className="flex flex-col items-center text-center gap-6 py-16">
            <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center">
              <Inbox className="h-8 w-8 text-primary" />
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-bold tracking-tight">Sin PRs analizados todavía</h2>
              <p className="text-muted-foreground text-sm max-w-md">
                Abre o actualiza un Pull Request en un repo con el webhook configurado — en
                cuanto llegue, aparecerá aquí con sus findings en vivo.
              </p>
            </div>
            <Button onClick={fetchStatus} variant="outline" size="sm" className="gap-2 mt-2">
              <RefreshCw className="h-3.5 w-3.5" />
              Actualizar
            </Button>
          </div>
        )}

        {/* Results */}
        {!loading && result && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* PR Info */}
            <PRCard
              number={result.pr.number}
              title={result.pr.title}
              author={result.pr.author}
              status={result.pr.status}
              repo={result.pr.repo}
            />

            {/* Score + Summary */}
            <div className="grid grid-cols-5 gap-2">
              <div className="col-span-1 flex flex-col items-center justify-center p-3 rounded-lg border bg-card">
                <span className="text-3xl font-bold">{result.summary.score}</span>
                <span className="text-[10px] text-muted-foreground uppercase">Score</span>
              </div>
              <div className="col-span-1 flex flex-col items-center justify-center p-3 rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/20">
                <span className="text-xl font-bold text-red-600 dark:text-red-400">{result.summary.critical}</span>
                <span className="text-[10px] text-muted-foreground">Critical</span>
              </div>
              <div className="col-span-1 flex flex-col items-center justify-center p-3 rounded-lg border border-orange-200 dark:border-orange-900/50 bg-orange-50 dark:bg-orange-950/20">
                <span className="text-xl font-bold text-orange-600 dark:text-orange-400">{result.summary.high}</span>
                <span className="text-[10px] text-muted-foreground">High</span>
              </div>
              <div className="col-span-1 flex flex-col items-center justify-center p-3 rounded-lg border border-yellow-200 dark:border-yellow-900/50 bg-yellow-50 dark:bg-yellow-950/20">
                <span className="text-xl font-bold text-yellow-600 dark:text-yellow-400">{result.summary.medium}</span>
                <span className="text-[10px] text-muted-foreground">Medium</span>
              </div>
              <div className="col-span-1 flex flex-col items-center justify-center p-3 rounded-lg border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/20">
                <span className="text-xl font-bold text-blue-600 dark:text-blue-400">{result.summary.low}</span>
                <span className="text-[10px] text-muted-foreground">Low</span>
              </div>
            </div>

            {/* Findings */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  Findings
                </h2>
                {result.pr.status === "analyzing" && (
                  <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 animate-pulse" />
                    actualizando en vivo
                  </span>
                )}
              </div>
              {result.findings.length === 0 && (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  {result.pr.status === "analyzing"
                    ? "Analizando... los findings aparecerán aquí a medida que se validen."
                    : "No se encontraron issues en esta revisión."}
                </p>
              )}
              {result.findings.map((finding, idx) => (
                <CommentPreview
                  key={idx}
                  file={finding.file}
                  line={finding.line}
                  severity={finding.severity}
                  issue={finding.issue}
                  suggestion={finding.suggestion}
                  category={finding.category}
                />
              ))}
            </div>

            {/* Manual refresh */}
            <div className="flex justify-center pt-4">
              <Button
                onClick={fetchStatus}
                variant="outline"
                size="sm"
                className="gap-2"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Actualizar
              </Button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
