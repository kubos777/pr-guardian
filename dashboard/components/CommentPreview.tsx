"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileCode, Lightbulb } from "lucide-react";

export type Severity = "critical" | "high" | "medium" | "low";

interface CommentPreviewProps {
  file: string;
  line: number;
  severity: Severity;
  issue: string;
  suggestion: string;
  category?: string;
}

const severityConfig: Record<
  Severity,
  { variant: "destructive" | "default" | "secondary" | "outline"; border: string; bg: string }
> = {
  critical: {
    variant: "destructive",
    border: "border-l-red-500",
    bg: "bg-red-500/5",
  },
  high: {
    variant: "default",
    border: "border-l-orange-500",
    bg: "bg-orange-500/5",
  },
  medium: {
    variant: "secondary",
    border: "border-l-yellow-500",
    bg: "bg-yellow-500/5",
  },
  low: {
    variant: "outline",
    border: "border-l-blue-500",
    bg: "bg-blue-500/5",
  },
};

export function CommentPreview({
  file,
  line,
  severity,
  issue,
  suggestion,
  category,
}: CommentPreviewProps) {
  const config = severityConfig[severity];

  return (
    <Card className={`border-l-4 ${config.border} ${config.bg}`}>
      <CardContent className="pt-4 space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-1.5 text-xs">
            <FileCode className="h-3.5 w-3.5 text-muted-foreground" />
            <code className="bg-muted px-1.5 py-0.5 rounded font-mono">
              {file}
            </code>
            <span className="text-muted-foreground">line {line}</span>
          </div>
          <div className="flex items-center gap-2">
            {category && (
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                {category}
              </span>
            )}
            <Badge variant={config.variant} className="text-[10px] uppercase">
              {severity}
            </Badge>
          </div>
        </div>

        {/* Issue */}
        <p className="text-sm font-medium">{issue}</p>

        {/* Suggestion */}
        <div className="flex items-start gap-2 text-xs text-muted-foreground bg-muted/50 rounded-md p-2.5">
          <Lightbulb className="h-3.5 w-3.5 mt-0.5 shrink-0 text-yellow-500" />
          <span>{suggestion}</span>
        </div>
      </CardContent>
    </Card>
  );
}
