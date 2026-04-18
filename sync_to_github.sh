#!/bin/bash
# Auto-sync HUBERT changes to GitHub after each Claude Code session

set -e

JARVIS_DIR="/Users/jakegoncalves/Jarvis"
CLAUDE_CONFIG_DIR="/Users/jakegoncalves/.claude"
CLAUDE_REPO_DIR="/Users/jakegoncalves/.claude-config-repo"

timestamp=$(date '+%Y-%m-%d %H:%M')

# ── 1. Sync Jarvis project ────────────────────────────────────────────────────
cd "$JARVIS_DIR"
if git remote get-url origin &>/dev/null; then
    # Stage modified tracked files (not untracked blobs)
    git add -u
    # Also stage known source files explicitly
    git add main.py cad_server.py cad_popup.py cad_ui.html \
            tools/custom/cad_tool.py \
            particle_server.py particle_simulator.html \
            tools/custom/particle_tool.py \
            jarvis_core.py claude_code_backend.py \
            ollama_core.py ollama_orchestrator.py ui_bridge.py \
            project_engine.py memory_pipeline.py file_upload_utils.py \
            config.py requirements.txt 2>/dev/null || true

    if ! git diff --cached --quiet; then
        git commit -m "auto-sync: HUBERT changes @ $timestamp"
    fi

    git push origin main --quiet && echo "[sync] Jarvis pushed to GitHub"
else
    echo "[sync] Jarvis: no remote set — skipping push (run: git remote add origin <url>)"
fi

# ── 2. Sync ~/.claude config ──────────────────────────────────────────────────
# Mirror key config files into a dedicated repo
mkdir -p "$CLAUDE_REPO_DIR/memory"

cp "$CLAUDE_CONFIG_DIR/CLAUDE.md" "$CLAUDE_REPO_DIR/" 2>/dev/null || true
cp "$CLAUDE_CONFIG_DIR/settings.json" "$CLAUDE_REPO_DIR/" 2>/dev/null || true

# Sync memory files
cp -r "$CLAUDE_CONFIG_DIR/projects/-Users-jakegoncalves-Jarvis/memory/." \
      "$CLAUDE_REPO_DIR/memory/" 2>/dev/null || true

cd "$CLAUDE_REPO_DIR"

if [ ! -d ".git" ]; then
    git init -q
    git config user.name "HUBERT"
    git config user.email "hubert@local"
    echo "# HUBERT Claude Config" > README.md
    echo ".DS_Store" > .gitignore
fi

git add -A
if ! git diff --cached --quiet; then
    git commit -m "auto-sync: config + memory @ $timestamp" -q
fi

if git remote get-url origin &>/dev/null; then
    git push origin main --quiet && echo "[sync] Claude config pushed to GitHub"
else
    echo "[sync] Config repo: no remote set — skipping push (run: cd ~/.claude-config-repo && git remote add origin <url>)"
fi
