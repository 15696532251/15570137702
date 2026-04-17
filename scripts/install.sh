#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

TOOL=""
CATEGORIES=()
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install Claude agents to your AI coding tool's agents directory.

Options:
  --tool <name>         Target tool: claude-code (required)
  --category <name>     Install only a specific category (can be repeated)
                        Available: engineering, data, security, devops
  --dry-run             Show what would be installed without copying files
  -h, --help            Show this help message

Examples:
  $(basename "$0") --tool claude-code
  $(basename "$0") --tool claude-code --category engineering
  $(basename "$0") --tool claude-code --category security --category devops
  $(basename "$0") --tool claude-code --dry-run
EOF
}

log()  { printf '\033[0;32m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m[warn]\033[0m %s\n' "$*"; }
err()  { printf '\033[0;31m[error]\033[0m %s\n' "$*" >&2; }

resolve_dest() {
  local tool="$1"
  case "$tool" in
    claude-code)
      echo "${HOME}/.claude/agents"
      ;;
    *)
      err "Unknown tool: '$tool'. Supported tools: claude-code"
      exit 1
      ;;
  esac
}

resolve_categories() {
  if [[ ${#CATEGORIES[@]} -eq 0 ]]; then
    local found=()
    for dir in "$REPO_ROOT"/*/; do
      local name
      name="$(basename "$dir")"
      [[ "$name" == "scripts" ]] && continue
      [[ -d "$dir" ]] && found+=("$name")
    done
    echo "${found[@]}"
  else
    echo "${CATEGORIES[@]}"
  fi
}

validate_categories() {
  local cats=("$@")
  for cat in "${cats[@]}"; do
    local dir="$REPO_ROOT/$cat"
    if [[ ! -d "$dir" ]]; then
      err "Category '$cat' not found in repository (looked at: $dir)"
      err "Available categories: $(ls -d "$REPO_ROOT"/*/ 2>/dev/null | xargs -n1 basename | grep -v scripts | tr '\n' ' ')"
      exit 1
    fi
  done
}

install_agents() {
  local dest="$1"
  shift
  local cats=("$@")
  local installed=0
  local skipped=0

  if [[ "$DRY_RUN" == false ]]; then
    mkdir -p "$dest"
  fi

  for cat in "${cats[@]}"; do
    local src_dir="$REPO_ROOT/$cat"
    local agent_files=()
    while IFS= read -r -d '' f; do
      agent_files+=("$f")
    done < <(find "$src_dir" -maxdepth 1 -name '*.md' -print0 2>/dev/null)

    if [[ ${#agent_files[@]} -eq 0 ]]; then
      warn "No .md files found in category '$cat', skipping."
      continue
    fi

    log "Category: $cat (${#agent_files[@]} agent(s))"

    for src in "${agent_files[@]}"; do
      local filename
      filename="$(basename "$src")"
      local dest_file="$dest/$filename"

      if [[ "$DRY_RUN" == true ]]; then
        printf '  \033[0;36m[dry-run]\033[0m would copy: %s → %s\n' "$src" "$dest_file"
        (( installed++ )) || true
      else
        if [[ -f "$dest_file" ]]; then
          warn "  Overwriting existing agent: $filename"
        fi
        cp "$src" "$dest_file"
        printf '  \033[0;32m✓\033[0m %s\n' "$filename"
        (( installed++ )) || true
      fi
    done
  done

  echo ""
  if [[ "$DRY_RUN" == true ]]; then
    log "Dry run complete. $installed agent(s) would be installed to: $dest"
  else
    log "Done. $installed agent(s) installed to: $dest"
    echo ""
    log "Activate an agent in Claude Code by telling it:"
    log "  \"Activate [agent-name] mode and help me with...\""
    log "  Example: \"Activate frontend-developer mode and build a React component\""
  fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tool)
      TOOL="${2:-}"
      [[ -z "$TOOL" ]] && { err "--tool requires a value"; exit 1; }
      shift 2
      ;;
    --category)
      CAT="${2:-}"
      [[ -z "$CAT" ]] && { err "--category requires a value"; exit 1; }
      CATEGORIES+=("$CAT")
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown option: $1"
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$TOOL" ]]; then
  err "--tool is required"
  usage >&2
  exit 1
fi

DEST="$(resolve_dest "$TOOL")"
mapfile -t RESOLVED_CATS < <(resolve_categories | tr ' ' '\n')
validate_categories "${RESOLVED_CATS[@]}"

echo ""
log "Installing agents for tool: $TOOL"
log "Destination: $DEST"
log "Categories: ${RESOLVED_CATS[*]}"
echo ""

install_agents "$DEST" "${RESOLVED_CATS[@]}"
