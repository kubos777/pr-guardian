#!/usr/bin/env bash
# Crea un PR de demo FRESCO (sin comentarios previos) en el demo-repo, para
# que cada grabación empiece con un "antes" limpio. Imprime el número de PR y
# el head_sha, más el comando listo para correr el demo contra ese PR.
#
# Requiere: GITHUB_TOKEN en el entorno (o en ../.env), y el clon del demo-repo.
set -euo pipefail

DEMO_REPO_DIR="${DEMO_REPO_DIR:-$HOME/Desktop/projects/cf-kiro-hackaton/pr-guardian-demo}"
REPO="kubos777/pr-guardian-demo"
BASE_BRANCH="ft/add-user-features"   # rama con los bugs sembrados

# token
if [ -z "${GITHUB_TOKEN:-}" ] && [ -f "$(dirname "$0")/../.env" ]; then
  set -a; source "$(dirname "$0")/../.env"; set +a
fi
[ -n "${GITHUB_TOKEN:-}" ] || { echo "Falta GITHUB_TOKEN"; exit 1; }

STAMP="$(date +%s)"
BRANCH="demo/run-$STAMP"

cd "$DEMO_REPO_DIR"
git fetch origin --quiet
git checkout -b "$BRANCH" "origin/$BASE_BRANCH" --quiet
printf '\n<!-- demo run %s -->\n' "$STAMP" >> README.md
git add README.md
git commit -m "chore: fresh demo run $STAMP" --quiet
git push -u origin "$BRANCH" --quiet
HEAD_SHA="$(git rev-parse HEAD)"

PR_JSON="$(curl -s -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/pulls" \
  -d "{\"title\":\"feat: add user features (orders, user service, shared types)\",\"head\":\"$BRANCH\",\"base\":\"main\",\"body\":\"Adds the first batch of user-related features. Feedback welcome.\"}")"

PR_NUM="$(printf '%s' "$PR_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("number",""))')"

echo ""
echo "✅ PR fresco creado: https://github.com/$REPO/pull/$PR_NUM"
echo ""
echo "Corre el demo contra este PR:"
echo ""
echo "  DEMO_PR=$PR_NUM DEMO_HEAD_SHA=$HEAD_SHA \\"
echo "  BASE_URL=https://54.90.206.50.nip.io \\"
echo "  uv run python scripts/demo_playwright.py"
echo ""
echo "(recuerda: ./scripts/reset_prod.sh antes, para que corra en vivo)"
