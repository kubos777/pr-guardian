"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { GitPullRequest, User, GitBranch } from "lucide-react";

export type PRStatus = "idle" | "analyzing" | "completed" | "failed";

interface PRCardProps {
  number: number;
  title: string;
  author: string;
  status: PRStatus;
  repo?: string;
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

export function PRCard({ number, title, author, status, repo }: PRCardProps) {
  const config = statusConfig[status];

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-primary">
            <GitPullRequest className="h-5 w-5" />
            <span className="font-mono font-bold text-lg">#{number}</span>
          </div>
          <Badge variant={config.variant} className="gap-1.5">
            <span className={`h-2 w-2 rounded-full ${config.dot}`} />
            {config.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="font-medium leading-snug">{title}</p>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <User className="h-3 w-3" />
            {author}
          </span>
          {repo && (
            <span className="flex items-center gap-1">
              <GitBranch className="h-3 w-3" />
              {repo}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
