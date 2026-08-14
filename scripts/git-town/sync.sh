#!/usr/bin/env bash
# Bounded no-push Git Town sync adapter (issue #18).
#
# Sequence: doctor -> capture before -> dry-run -> live -> capture after ->
# independent verification -> append-only receipt. Every step is a typed
# operation in scripts/git-town/receipt.py; this file owns ordering, selector
# resolution, cleanup and status propagation only.
#
# It never resolves conflicts, edits conflict markers, continues, skips, undoes,
# ships, resets, deletes a branch, or pushes. On a blocked outcome the worktree
# and the intermediate evidence are preserved for human review.
#
#   sync.sh --head-branch B --allowed-path P [--allowed-path P]... \
#           [--excluded-path P]... [--timeout-seconds N] [--receipts-root DIR] \
#           [--dry-run-only]
#   sync.sh --selftest

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RECEIPT="${SCRIPT_DIR}/receipt.py"
DOCTOR="${SCRIPT_DIR}/doctor.sh"
TOOL_SELECTOR="HOST_GIT_TOWN_BIN"
PYTHON_BIN="${PYTHON:-python3}"

head_branch=""
timeout_seconds="900"
receipts_root=""
dry_run_only="false"
skip_doctor="false"
selftest="false"
allowed_paths=()
excluded_paths=()

evidence_dir=""
preserve_evidence="false"

blocked() {
  printf '%s\n' "$2" >&2
  printf '{"result":"%s"}\n' "$1"
  exit 1
}

cleanup() {
  # Cleanup never destroys blocked evidence: a preserved conflict lane is the
  # only thing a human has to work from.
  if [ -n "${evidence_dir}" ] && [ -d "${evidence_dir}" ]; then
    if [ "${preserve_evidence}" = "true" ]; then
      printf 'preserved sync evidence: %s\n' "${evidence_dir}" >&2
    else
      rm -rf -- "${evidence_dir}"
    fi
  fi
}
trap cleanup EXIT

while [ "$#" -gt 0 ]; do
  case "$1" in
    --head-branch) head_branch="${2:-}"; shift 2 ;;
    --allowed-path) allowed_paths+=("${2:-}"); shift 2 ;;
    --excluded-path) excluded_paths+=("${2:-}"); shift 2 ;;
    --timeout-seconds) timeout_seconds="${2:-}"; shift 2 ;;
    --receipts-root) receipts_root="${2:-}"; shift 2 ;;
    --dry-run-only) dry_run_only="true"; shift ;;
    --skip-doctor) skip_doctor="true"; shift ;;
    --selftest) selftest="true"; shift ;;
    *) blocked "BLOCKED_POLICY" "unsupported argument: $1" ;;
  esac
done

if [ "${selftest}" = "true" ]; then
  "${PYTHON_BIN}" "${RECEIPT}" --selftest
  if HOST_GIT_TOWN_BIN="" "$0" --head-branch x --allowed-path y --skip-doctor >/dev/null 2>&1; then
    printf 'sync selftest: an unresolved tool selector must block\n' >&2
    exit 1
  fi
  if "$0" --allowed-path y >/dev/null 2>&1; then
    printf 'sync selftest: a missing head branch must block\n' >&2
    exit 1
  fi
  if "$0" --continue >/dev/null 2>&1; then
    printf 'sync selftest: an unsupported argument must block\n' >&2
    exit 1
  fi
  printf 'sync selftest: PASS\n' >&2
  exit 0
fi

[ -n "${head_branch}" ] || blocked "BLOCKED_POLICY" "--head-branch is required"
[ "${#allowed_paths[@]}" -gt 0 ] || blocked "BLOCKED_POLICY" "at least one --allowed-path is required"
[ "${timeout_seconds}" -gt 0 ] 2>/dev/null ||
  blocked "BLOCKED_POLICY" "--timeout-seconds must be a positive integer"

tool="${!TOOL_SELECTOR:-}"
[ -n "${tool}" ] || blocked "BLOCKED_TOOL_ADMISSION" \
  "logical tool selector ${TOOL_SELECTOR} is unresolved; issue #15 has not admitted a host executable"

repository="$(git rev-parse --show-toplevel)"
[ -n "${receipts_root}" ] || receipts_root="${repository}/receipts/git-town/sync"

if [ "${skip_doctor}" = "false" ]; then
  doctor_arguments=(--head-branch "${head_branch}")
  for path in "${allowed_paths[@]}"; do
    doctor_arguments+=(--allowed-path "${path}")
  done
  # The doctor's own receipt goes to stderr context; its status is the gate.
  bash "${DOCTOR}" "${doctor_arguments[@]}" >/dev/null || exit 1
fi

evidence_dir="$(mktemp -d)"

run_receipt() {
  # $1 output file, rest: typed operation arguments.
  local output="$1"; shift
  if ! "${PYTHON_BIN}" "${RECEIPT}" "$@" --repository "${repository}" >"${output}"; then
    preserve_evidence="true"
    cat "${output}"
    exit 1
  fi
}

run_receipt "${evidence_dir}/before.json" capture --head-branch "${head_branch}"

# Step 2 — dry-run first. A live command never runs before this passes.
"${PYTHON_BIN}" "${RECEIPT}" sync --tool "${tool}" --mode dry-run \
  --timeout-seconds "${timeout_seconds}" --repository "${repository}" \
  >"${evidence_dir}/dry-run.json" || true
dry_run_result="$("${PYTHON_BIN}" -c \
  'import json,sys;print(json.load(open(sys.argv[1]))["result"])' "${evidence_dir}/dry-run.json")"
if [ "${dry_run_result}" != "PASS" ]; then
  preserve_evidence="true"
  printf 'dry run did not pass: %s\n' "${dry_run_result}" >&2
  printf '{"result":"%s"}\n' "${dry_run_result}"
  exit 1
fi

if [ "${dry_run_only}" = "true" ]; then
  printf '{"result":"PASS","stage":"dry-run"}\n'
  exit 0
fi

# Step 3 — bounded no-push sync, same executable, scope, flags and timeout.
"${PYTHON_BIN}" "${RECEIPT}" sync --tool "${tool}" --mode live \
  --timeout-seconds "${timeout_seconds}" --repository "${repository}" \
  >"${evidence_dir}/live.json" || true
live_result="$("${PYTHON_BIN}" -c \
  'import json,sys;print(json.load(open(sys.argv[1]))["result"])' "${evidence_dir}/live.json")"
if [ "${live_result}" != "PASS" ]; then
  # BLOCKED_CONFLICT, BLOCKED_PROMPT, BLOCKED_TIMEOUT or FAILED_TOOL. Preserve
  # the worktree and evidence; no continuation command is ever attempted.
  preserve_evidence="true"
  printf 'sync did not complete: %s\n' "${live_result}" >&2
  printf '{"result":"%s"}\n' "${live_result}"
  exit 1
fi

run_receipt "${evidence_dir}/after.json" capture --head-branch "${head_branch}"

# Step 4 — verification runs independently of the path that mutated.
verify_arguments=(
  verify
  --before "${evidence_dir}/before.json"
  --after "${evidence_dir}/after.json"
  --dry-run-record "${evidence_dir}/dry-run.json"
  --live-record "${evidence_dir}/live.json"
)
for path in "${allowed_paths[@]}"; do
  verify_arguments+=(--allowed-path "${path}")
done
if [ "${#excluded_paths[@]}" -gt 0 ]; then
  for path in "${excluded_paths[@]}"; do
    verify_arguments+=(--excluded-path "${path}")
  done
fi
run_receipt "${evidence_dir}/verification.json" "${verify_arguments[@]}"

run_receipt "${evidence_dir}/receipt.json" append \
  --before "${evidence_dir}/before.json" \
  --after "${evidence_dir}/after.json" \
  --dry-run-record "${evidence_dir}/dry-run.json" \
  --live-record "${evidence_dir}/live.json" \
  --verification "${evidence_dir}/verification.json" \
  --receipts-root "${receipts_root}"

cat "${evidence_dir}/receipt.json"
