#!/usr/bin/env bash
# Install the ui-ux-pro-max Claude skill into .claude/skills/ui-ux-pro-max.
#
# The skill ships ~2MB of design databases (CSV) that we do not vendor in git.
# This script fetches it from upstream and is idempotent: it exits early if the
# skill is already present. It is wired to run on SessionStart (see
# .claude/settings.json) so the skill is available in fresh / ephemeral
# environments.
#
# Upstream: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
set -euo pipefail

SKILLS_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$SKILLS_DIR/ui-ux-pro-max"

# Already installed -> nothing to do.
if [ -f "$DEST/SKILL.md" ] && [ -f "$DEST/scripts/search.py" ]; then
  exit 0
fi

CA="/root/.ccr/ca-bundle.crt"
CAOPT=()
[ -f "$CA" ] && CAOPT=(--cacert "$CA")

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

URL="https://codeload.github.com/nextlevelbuilder/ui-ux-pro-max-skill/tar.gz/refs/heads/main"
if ! curl -fsSL "${CAOPT[@]}" "$URL" -o "$TMP/skill.tgz"; then
  echo "install-ui-ux-pro-max: download failed (network restricted?)" >&2
  exit 0  # do not fail the session
fi

tar xzf "$TMP/skill.tgz" -C "$TMP"
SRC="$TMP/ui-ux-pro-max-skill-main/.claude/skills/ui-ux-pro-max"
if [ ! -d "$SRC" ]; then
  echo "install-ui-ux-pro-max: unexpected archive layout" >&2
  exit 0
fi

mkdir -p "$SKILLS_DIR"
rm -rf "$DEST"
# -L dereferences the scripts/ and data/ symlinks the repo uses into real files.
cp -rL "$SRC" "$DEST"
echo "install-ui-ux-pro-max: installed ui-ux-pro-max skill into $DEST"
