"use client";

import { Check, X } from "lucide-react";
import type { PRStatus } from "@/components/PRCard";

// Mirrors store/stages.py: the worker executes these four stages as
// chained Celery tasks (see ARCHITECTURE_DIAGRAMS.md). RECEIVED/QUEUED
// happen before the first of these; COMPLETED/FAILED are terminal.
const STEPS = [
  { key: "FETCHING_CONTEXT", label: "Fetching Context" },
  { key: "ANALYZING", label: "Analyzing" },
  { key: "VALIDATING", label: "Validating" },
  { key: "POSTING_TO_GITHUB", label: "Posting to GitHub" },
] as const;

export type BackendStage =
  | "RECEIVED"
  | "QUEUED"
  | "FETCHING_CONTEXT"
  | "ANALYZING"
  | "VALIDATING"
  | "POSTING_TO_GITHUB"
  | "COMPLETED"
  | "FAILED";

interface PipelineStepperProps {
  status: PRStatus;
  stage: BackendStage;
}

export function PipelineStepper({ status, stage }: PipelineStepperProps) {
  const activeIndex = STEPS.findIndex((s) => s.key === stage);

  if (status === "failed") {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-2.5">
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-destructive/15">
          <X className="h-3 w-3 text-destructive" />
        </div>
        <p className="text-xs text-muted-foreground">
          El pipeline se detuvo antes de completar sus 4 etapas — ver el mensaje de error arriba.
        </p>
      </div>
    );
  }

  return (
    <div
      role="list"
      aria-label="Progreso del pipeline de revisión"
      className="flex items-start justify-between gap-1"
    >
      {STEPS.map((step, i) => {
        const isDone = status === "completed" || (activeIndex !== -1 && i < activeIndex);
        const isActive = status !== "completed" && i === activeIndex;
        const isLast = i === STEPS.length - 1;

        return (
          <div key={step.key} role="listitem" className="flex flex-1 items-start last:flex-none">
            <div className="flex flex-col items-center gap-1.5" style={{ minWidth: 0 }}>
              <div
                className={[
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold transition-colors",
                  isDone
                    ? "border-primary bg-primary text-primary-foreground"
                    : isActive
                    ? "border-primary bg-primary/10 text-primary animate-pulse"
                    : "border-border bg-muted text-muted-foreground",
                ].join(" ")}
                aria-current={isActive ? "step" : undefined}
              >
                {isDone ? <Check className="h-3 w-3" /> : i + 1}
              </div>
              <span
                className={[
                  "text-center text-[10px] leading-tight",
                  isDone || isActive ? "text-foreground font-medium" : "text-muted-foreground",
                ].join(" ")}
              >
                {step.label}
              </span>
            </div>
            {!isLast && (
              <div
                className={[
                  "mt-3 h-px flex-1 shrink transition-colors",
                  isDone ? "bg-primary" : "bg-border",
                ].join(" ")}
                style={{ marginInline: 4 }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
