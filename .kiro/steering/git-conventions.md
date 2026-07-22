---
inclusion: always
---

# Git Conventions — PR Guardian

## Branch Naming

All branches MUST be created from `main`. Use the following prefixes:

| Prefix | Purpose | Example |
|--------|---------|---------|
| `ft/`  | New feature | `ft/agent-core-setup` |
| `hx/`  | Hotfix (urgent production fix) | `hx/webhook-timeout` |
| `fx/`  | Bug fix (non-urgent) | `fx/null-check-handler` |

Rules:
- Always branch from `main` (never from another feature branch).
- Use kebab-case after the prefix.
- Keep branch names short and descriptive.

## Commit Messages

All commits MUST follow Conventional Commits format and be written in **English**.

```
<type>: <short description in English>
```

### Allowed types

| Type | When to use |
|------|-------------|
| `feat:` | Adding new functionality |
| `fix:` | Fixing a bug |
| `hotfix:` | Urgent fix for production |
| `docs:` | Documentation only changes |
| `chore:` | Tooling, config, dependencies |
| `refactor:` | Code change that neither fixes a bug nor adds a feature |
| `test:` | Adding or updating tests |
| `style:` | Formatting, whitespace (no logic change) |

### Rules
- First letter after the colon is **lowercase**.
- No period at the end.
- Max 72 characters for the subject line.
- Language: **English only** (judges will review the repo).

### Examples

```
feat: add webhook handler for PR events
fix: resolve null reference in diff parser
hotfix: patch auth token expiration check
docs: update README with architecture diagram
chore: add eslint config for dashboard
```

## Pull Requests

- PR title follows the same commit format: `feat: description`
- PR description should include what changed and why.
- Target branch is always `main`.
