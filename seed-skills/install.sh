#!/usr/bin/env bash
# Install seed-skills/ entries into data/skills/<category>/<name>/
# for one or more Odysseus users.
#
# Odysseus skills are strictly owner-scoped (see services/memory/skills.py
# line 261: a skill with `owner: X` in its frontmatter is invisible to
# anyone else, and ownerless skills are invisible to everyone). So a
# shared "shipped with the repo" skill needs to be materialized per-user
# with that user's name baked into the frontmatter.
#
# Usage (from the repo root, on the running Odysseus box):
#   seed-skills/install.sh igor daria
#
# Re-running is idempotent: existing skill files are overwritten with
# the latest seed content, BUT the usage sidecar (_usage.json) is left
# alone so each user's "times used" counter persists.

set -euo pipefail

if [ $# -eq 0 ]; then
  echo "Usage: $0 <username> [<username> ...]" >&2
  echo "Example: $0 igor daria" >&2
  exit 2
fi

# Resolve to the data/skills root relative to where this script lives,
# so it works regardless of cwd.
SEED_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SEED_DIR/.." && pwd)"
SKILLS_ROOT="$APP_DIR/data/skills"

if [ ! -d "$APP_DIR/data" ]; then
  echo "ERROR: $APP_DIR/data does not exist — is this an Odysseus checkout that has been set up?" >&2
  exit 2
fi

mkdir -p "$SKILLS_ROOT"

# Walk every seed-skills/<slug>/SKILL.md and install per user.
shopt -s nullglob
seed_skills=("$SEED_DIR"/*/SKILL.md)
if [ ${#seed_skills[@]} -eq 0 ]; then
  echo "No SKILL.md files found under $SEED_DIR" >&2
  exit 0
fi

for user in "$@"; do
  for src in "${seed_skills[@]}"; do
    base_name="$(basename "$(dirname "$src")")"
    # Skills are owner-scoped via frontmatter but stored at a flat path
    # keyed by the `name:` slug. Two users sharing one slug collide on
    # disk (the second install would overwrite the first). Per-user
    # naming keeps both copies, both visible only to their owner.
    per_user_name="${base_name}-${user}"
    # Read the category from the frontmatter; default to general.
    category="$(awk '/^category:/ {print $2; exit}' "$src" 2>/dev/null || true)"
    category="${category:-general}"
    dest_dir="$SKILLS_ROOT/$category/$per_user_name"
    dest="$dest_dir/SKILL.md"
    mkdir -p "$dest_dir"
    # Atomic write — sed into a tmp file in the destination dir, then
    # rename onto the target so a concurrent loader never sees a
    # half-written SKILL.md. Swap BOTH the placeholder owner and the
    # `name:` slug so the loader keys the file correctly.
    tmp="$dest.tmp.$$"
    sed \
      -e "s/^owner: REPLACE_WITH_YOUR_USERNAME$/owner: $user/" \
      -e "s/^name: ${base_name}$/name: ${per_user_name}/" \
      "$src" > "$tmp"
    mv -f "$tmp" "$dest"
    echo "installed: $category/$per_user_name → owner=$user"
  done
done

echo ""
echo "Done. Reload the Skills tab in Odysseus to see them, or restart the"
echo "service so the agent picks them up on its next turn:"
echo "  sudo systemctl restart odysseus"
