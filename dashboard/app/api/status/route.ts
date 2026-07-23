import { NextResponse } from "next/server";

// Dummy response simulating a PR analysis result
export async function GET() {
  return NextResponse.json({
    pr: {
      number: 7,
      title: "feat: add user validation to signup endpoint",
      author: "dev-junior",
      repo: "kubos777/pr-guardian",
      status: "completed",
    },
    findings: [
      {
        file: "src/api/users.ts",
        line: 23,
        severity: "critical",
        category: "A03:Injection",
        issue: "User input concatenated directly into SQL query",
        suggestion:
          "Use parameterized queries: db.query('SELECT * FROM users WHERE id = $1', [userId])",
      },
      {
        file: "src/config/settings.ts",
        line: 8,
        severity: "high",
        category: "Hardcoded Secret",
        issue: "API key stored as plaintext string literal",
        suggestion: "Move to environment variable: process.env.API_KEY",
      },
      {
        file: "src/utils/parser.ts",
        line: 42,
        severity: "medium",
        category: "Style",
        issue: "Variable name uses abbreviation instead of full word",
        suggestion: "Rename `usr` to `user` for clarity",
      },
      {
        file: "src/services/db.ts",
        line: 15,
        severity: "low",
        category: "Performance",
        issue: "Database call inside a loop — potential N+1 query",
        suggestion:
          "Batch the query outside the loop using Promise.all or a single WHERE IN clause",
      },
    ],
    summary: {
      total: 4,
      critical: 1,
      high: 1,
      medium: 1,
      low: 1,
      score: 4,
    },
  });
}
