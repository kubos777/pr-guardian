"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { GitPullRequest, User, GitBranch, ExternalLink, Clock } from "lucide-react";

export type PRStatus = "idle" | "analyzing" | "completed" | "failed";

interface PRCardProps {
  number: number;
  title: string;
  author: string;
  status: PRStatus;
  repo?: string;
  updatedAt?: string;
}

function formatCompletedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-MX", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

const statusConfig: Record<
  PRStatus,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline"; dot: string }
> = {
  idle: { label: "Idle", variant: "outline", dot: "bg-gray-400" },
  analyzing: { label: "Analyzing", variant: "secondary", dot: "bg-yellow-400 animate-pulse" },
  completed: { label: "Completed", variant: "default", dot: "bg-green-400" },
  failed: { label: "Failed", variant: "destructive", dot: "bg-red-400" },
};

export function PRCard({ number, title, author, status, repo, updatedAt }: PRCardProps) {
  const config = statusConfig[status];
  const isTerminal = status === "completed" || status === "failed";
  const githubUrl = repo ? `https://github.com/${repo}/pull/${number}` : undefined;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-primary">
            <GitPullRequest className="h-5 w-5 shrink-0" />
            <span className="font-mono font-bold text-lg">#{number}</span>
          </div>
          <Badge variant={config.variant} className="gap-1.5 shrink-0">
            <span className={`h-2 w-2 rounded-full ${config.dot}`} />
            {config.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="font-medium leading-snug">{title}</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <User className="h-3 w-3" />
            {author}
          </span>
          {repo && (
            <span className="flex items-center gap-1 min-w-0">
              <GitBranch className="h-3 w-3 shrink-0" />
              <span className="truncate">{repo}</span>
            </span>
          )}
          {isTerminal && updatedAt && (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatCompletedAt(updatedAt)}
            </span>
          )}
        </div>
        {githubUrl && (
          <a
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline underline-offset-2"
          >
            <ExternalLink className="h-3 w-3" />
            Ver en GitHub
          </a>
        )}
      </CardContent>
    </Card>
  );
}
