#!/usr/bin/env bash
# collect_and_push.sh
# Collects Vélo'v station data locally, appends to local data/history.csv,
# updates README.md and SVG charts in assets/, and pushes ONLY the modified
# SVGs and README to GitHub. Large CSV files remain strictly local.

set -euo pipefail

# Ensure non-interactive git commands never hang on credential prompts
export GIT_TERMINAL_PROMPT=0

# Determine repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Starting Vélo'v collection routine..."

# 1. Load environment variables from .env if present
if [ -f "${REPO_DIR}/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${REPO_DIR}/.env"
    set +a
fi

# 2. Check for JCD_API_KEY
if [ -z "${JCD_API_KEY:-}" ]; then
    log "ERROR: JCD_API_KEY is not set. Please add it to ${REPO_DIR}/.env"
    exit 1
fi

# 3. Locate Python executable in virtual environment
PYTHON_BIN="${REPO_DIR}/.venv/bin/python"
if [ ! -x "${PYTHON_BIN}" ]; then
    PYTHON_BIN="$(which python3)"
fi

# 4. Sync upstream changes if git remote is configured
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")"
if git remote get-url origin >/dev/null 2>&1; then
    log "Syncing remote branch origin/${BRANCH}..."
    git fetch origin "${BRANCH}" 2>&1 || log "Warning: git fetch failed (offline or network issue)."
    
    # If our local branch is strictly behind remote, fast-forward/rebase
    LOCAL_HASH=$(git rev-parse HEAD 2>/dev/null || echo "")
    REMOTE_HASH=$(git rev-parse "origin/${BRANCH}" 2>/dev/null || echo "")
    BASE_HASH=$(git merge-base HEAD "origin/${BRANCH}" 2>/dev/null || echo "")
    
    if [ -n "${LOCAL_HASH}" ] && [ -n "${REMOTE_HASH}" ] && [ "${LOCAL_HASH}" != "${REMOTE_HASH}" ]; then
        if [ "${LOCAL_HASH}" = "${BASE_HASH}" ]; then
            log "Local branch is behind origin/${BRANCH}. Fast-forwarding..."
            git pull --rebase origin "${BRANCH}" || log "Warning: git pull rebase failed."
        fi
    fi
fi

# 5. Run the collection script (appends locally to data/history.csv, updates README.md and assets/*.svg)
log "Running collector with ${PYTHON_BIN}..."
"${PYTHON_BIN}" -m source.collect

# 6. Safety check: ensure data/ or CSV files are NEVER staged
git reset HEAD -- data/ 2>/dev/null || true

# 7. Check if README.md or any SVG in assets/ has changed
CHANGES=$(git status --porcelain README.md assets/ 2>/dev/null || true)
if [ -z "${CHANGES}" ]; then
    log "No changes detected in README.md or assets/*.svg. Nothing to commit."
    exit 0
fi

# 8. Stage ONLY README.md and SVG files
git add README.md assets/*.svg
# Enforce again: unstage data/ if accidentally added
git reset HEAD -- data/ 2>/dev/null || true

# Check if there are staged changes ready for commit
if git diff --staged --quiet; then
    log "No staged changes to commit."
    exit 0
fi

# 9. Configure git user for automated commits if not configured
if [ -z "$(git config user.name 2>/dev/null || true)" ]; then
    git config user.name "Lincoln Kermit"
fi
if [ -z "$(git config user.email 2>/dev/null || true)" ]; then
    git config user.email "104798220+LincolnKermit@users.noreply.github.com"
fi

COMMIT_MSG="data: Vélo'v snapshot [skip ci]"
log "Committing changes: ${COMMIT_MSG}"
git commit -m "${COMMIT_MSG}"

# 10. Push commits to GitHub (with retries if remote moved)
if git remote get-url origin >/dev/null 2>&1; then
    PUSHED=false
    for attempt in 1 2 3; do
        log "Pushing to GitHub (attempt ${attempt}/3)..."
        if git push origin "${BRANCH}"; then
            log "Successfully pushed to GitHub on attempt ${attempt}."
            PUSHED=true
            break
        else
            log "Push failed on attempt ${attempt}. Waiting before retry..."
            sleep 3
            git pull --rebase origin "${BRANCH}" 2>&1 || true
        fi
    done

    if [ "${PUSHED}" = false ]; then
        log "WARNING: Failed to push to GitHub after 3 attempts. Local data has been saved safely."
        exit 1
    fi
else
    log "No origin remote configured. Local commit created without push."
fi

log "Collection routine finished successfully."
