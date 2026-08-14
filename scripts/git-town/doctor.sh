#!/usr/bin/env bash
# Worktree and branch-lease doctor (issue #17).
#
# This script only orchestrates fixed Git commands and hands the facts to
# scripts/git-town/lease.py, which is the typed judge. It never resolves
# conflicts, mutates refs, pushes, or runs Git Town.
#
# The lease root is resolved from the logical selector in
# docs/git/REPO_PROFILE.md (lease_root_selector: host_llm_arbitrage_leases), so
# no host-specific absolute path is committed.
#
#   doctor.sh --head-branch B --allowed-path P [--allowed-path P]... \
#             [--holder ID] [--ttl-seconds N] [--now EPOCH]
#   doctor.sh --selftest

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LEASE_JUDGE="${SCRIPT_DIR}/lease.py"
LEASE_ROOT_SELECTOR="HOST_LLM_ARBITRAGE_LEASES"
PYTHON_BIN="${PYTHON:-python3}"

DOCTOR_SCHEMA="llm-arbitrage/worktree-doctor-receipt/v1"

head_branch=""
holder=""
ttl_seconds="3600"
now=""
allowed_paths=()
selftest="false"

blocked() {
  # One stable blocked result on stdout, the reason on stderr. Keeping the
  # shapes identical to the judge's means a caller never has to know whether
  # the shell or the judge refused.
  printf '%s\n' "$2" >&2
  printf '{"result":"%s","schema":"%s"}\n' "$1" "${DOCTOR_SCHEMA}"
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --head-branch) head_branch="${2:-}"; shift 2 ;;
    --allowed-path) allowed_paths+=("${2:-}"); shift 2 ;;
    --holder) holder="${2:-}"; shift 2 ;;
    --ttl-seconds) ttl_seconds="${2:-}"; shift 2 ;;
    --now) now="${2:-}"; shift 2 ;;
    --selftest) selftest="true"; shift ;;
    *) blocked "BLOCKED_POLICY" "unsupported argument: $1" ;;
  esac
done

if [ "${selftest}" = "true" ]; then
  # The judge owns the lease and remote laws; this layer's own contract is that
  # it refuses to run without a resolved selector and a head branch.
  "${PYTHON_BIN}" "${LEASE_JUDGE}" --selftest
  if HOST_LLM_ARBITRAGE_LEASES="" "$0" --head-branch x --allowed-path y >/dev/null 2>&1; then
    printf 'doctor selftest: an unresolved lease selector must block\n' >&2
    exit 1
  fi
  if "$0" --allowed-path y >/dev/null 2>&1; then
    printf 'doctor selftest: a missing head branch must block\n' >&2
    exit 1
  fi
  if "$0" --not-a-flag >/dev/null 2>&1; then
    printf 'doctor selftest: an unsupported argument must block\n' >&2
    exit 1
  fi
  printf 'doctor selftest: PASS\n' >&2
  exit 0
fi

[ -n "${head_branch}" ] || blocked "BLOCKED_POLICY" "--head-branch is required"
[ "${#allowed_paths[@]}" -gt 0 ] || blocked "BLOCKED_POLICY" "at least one --allowed-path is required"

lease_root="${!LEASE_ROOT_SELECTOR:-}"
[ -n "${lease_root}" ] || blocked "BLOCKED_POLICY" \
  "logical lease selector ${LEASE_ROOT_SELECTOR} is unresolved on this host"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
  blocked "BLOCKED_POLICY" "doctor must run inside a Git work tree"

git_dir="$(git rev-parse --absolute-git-dir)"
git_common_dir="$(cd -- "$(git rev-parse --git-common-dir)" && pwd)"

current_branch="$(git symbolic-ref --quiet --short HEAD || true)"
[ -n "${current_branch}" ] ||
  blocked "BLOCKED_ANCESTRY" "worktree HEAD is detached; a Worker must be on its declared head branch"

git remote get-url origin >/dev/null 2>&1 ||
  blocked "BLOCKED_POLICY" "origin remote is not configured"

dirty_entries="$(git status --porcelain | wc -l | tr -d '[:space:]')"

[ -n "${holder}" ] || holder="$(git rev-parse --absolute-git-dir)"

judge_arguments=(
  doctor
  --lease-root "${lease_root}"
  --head-branch "${head_branch}"
  --current-branch "${current_branch}"
  --git-dir "${git_dir}"
  --git-common-dir "${git_common_dir}"
  --dirty-entries "${dirty_entries}"
  --holder "${holder}"
  --ttl-seconds "${ttl_seconds}"
  --remote-url-from-stdin
)
for path in "${allowed_paths[@]}"; do
  judge_arguments+=(--allowed-path "${path}")
done
[ -z "${now}" ] || judge_arguments+=(--now "${now}")

# The origin URL travels on stdin, never in argv: rejecting a credential-bearing
# remote is one of this doctor's jobs, and argv is visible in the process table.
git remote get-url origin | "${PYTHON_BIN}" "${LEASE_JUDGE}" "${judge_arguments[@]}"
