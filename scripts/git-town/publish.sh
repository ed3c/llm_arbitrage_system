#!/usr/bin/env bash
# Publication gate binding and post-push verification driver (issue #20).
#
# This script decides; it never publishes. `worker_publication_enabled` is
# false in docs/git/REPO_PROFILE.md, so no push, PR-ready transition, workflow
# rerun or merge happens here. An ALLOW result names one operation for a human
# or operator to perform, and is spent the moment it is issued.
#
#   publish.sh --intent I --head-branch B --receipt R.json --snapshot S.json \
#              [--processed-feedback CURSOR]... [--decisions-ledger DIR]
#   publish.sh --verify-remote --head-branch B --expected-head-sha SHA \
#              [--expected-parent-sha SHA] [--protected-before BRANCH=SHA]...
#   publish.sh --selftest

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GATE="${SCRIPT_DIR}/github_snapshot.py"
REMOTE_VERIFY="${SCRIPT_DIR}/remote_verify.py"
LEDGER_SELECTOR="HOST_LLM_ARBITRAGE_DECISIONS"
PYTHON_BIN="${PYTHON:-python3}"

DECISION_SCHEMA="llm-arbitrage/publication-decision/v1"

intent=""
head_branch=""
receipt=""
snapshot=""
decisions_ledger=""
expected_head_sha=""
expected_parent_sha=""
remote="origin"
verify_remote="false"
selftest="false"
processed_feedback=()
protected_before=()

blocked() {
  printf '%s\n' "$2" >&2
  printf '{"decision":"%s","schema":"%s"}\n' "$1" "${DECISION_SCHEMA}"
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --intent) intent="${2:-}"; shift 2 ;;
    --head-branch) head_branch="${2:-}"; shift 2 ;;
    --receipt) receipt="${2:-}"; shift 2 ;;
    --snapshot) snapshot="${2:-}"; shift 2 ;;
    --processed-feedback) processed_feedback+=("${2:-}"); shift 2 ;;
    --decisions-ledger) decisions_ledger="${2:-}"; shift 2 ;;
    --remote) remote="${2:-}"; shift 2 ;;
    --expected-head-sha) expected_head_sha="${2:-}"; shift 2 ;;
    --expected-parent-sha) expected_parent_sha="${2:-}"; shift 2 ;;
    --protected-before) protected_before+=("${2:-}"); shift 2 ;;
    --verify-remote) verify_remote="true"; shift ;;
    --selftest) selftest="true"; shift ;;
    *) blocked "BLOCKED_POLICY" "unsupported argument: $1" ;;
  esac
done

if [ "${selftest}" = "true" ]; then
  "${PYTHON_BIN}" "${GATE}" --selftest
  "${PYTHON_BIN}" "${REMOTE_VERIFY}" --selftest
  if "$0" --push >/dev/null 2>&1; then
    printf 'publish selftest: an unsupported argument must block\n' >&2
    exit 1
  fi
  if "$0" --intent initial-pr >/dev/null 2>&1; then
    printf 'publish selftest: a gate call without its evidence must block\n' >&2
    exit 1
  fi
  printf 'publish selftest: PASS\n' >&2
  exit 0
fi

[ -n "${head_branch}" ] || blocked "BLOCKED_POLICY" "--head-branch is required"

if [ "${verify_remote}" = "true" ]; then
  [ -n "${expected_head_sha}" ] || blocked "BLOCKED_POLICY" "--expected-head-sha is required"
  verify_arguments=(
    --remote "${remote}"
    --head-branch "${head_branch}"
    --expected-head-sha "${expected_head_sha}"
  )
  [ -z "${expected_parent_sha}" ] || verify_arguments+=(--expected-parent-sha "${expected_parent_sha}")
  if [ "${#protected_before[@]}" -gt 0 ]; then
    for entry in "${protected_before[@]}"; do
      verify_arguments+=(--protected-before "${entry}")
    done
  fi
  exec "${PYTHON_BIN}" "${REMOTE_VERIFY}" --repository "$(git rev-parse --show-toplevel)" \
    "${verify_arguments[@]}"
fi

[ -n "${intent}" ] || blocked "BLOCKED_POLICY" "--intent is required"
[ -n "${receipt}" ] || blocked "BLOCKED_POLICY" "--receipt is required"
[ -n "${snapshot}" ] || blocked "BLOCKED_POLICY" "--snapshot is required"

[ -n "${decisions_ledger}" ] || decisions_ledger="${!LEDGER_SELECTOR:-}"
[ -n "${decisions_ledger}" ] || blocked "BLOCKED_POLICY" \
  "logical decisions selector ${LEDGER_SELECTOR} is unresolved on this host"

local_head="$(git rev-parse HEAD)"
current_branch="$(git symbolic-ref --quiet --short HEAD || true)"
[ "${current_branch}" = "${head_branch}" ] ||
  blocked "BLOCKED_POLICY" "the repository is on ${current_branch:-a detached HEAD}, not ${head_branch}"

gate_arguments=(
  evaluate
  --intent "${intent}"
  --snapshot "${snapshot}"
  --receipt "${receipt}"
  --local-head-sha "${local_head}"
)
if [ "${#processed_feedback[@]}" -gt 0 ]; then
  for cursor in "${processed_feedback[@]}"; do
    gate_arguments+=(--processed-feedback "${cursor}")
  done
fi

decision_file="$(mktemp)"
if ! "${PYTHON_BIN}" "${GATE}" "${gate_arguments[@]}" >"${decision_file}"; then
  cat "${decision_file}"
  rm -f -- "${decision_file}"
  exit 1
fi

decision_digest="$("${PYTHON_BIN}" -c \
  'import json,sys;print(json.load(open(sys.argv[1]))["decision_sha256"])' "${decision_file}")"

# One ALLOW authorizes one operation. Spending it is recorded before it is
# returned, so a replay of the same decision cannot buy a second operation.
mkdir -p -- "${decisions_ledger}"
spent="${decisions_ledger}/${decision_digest}.json"
if [ -e "${spent}" ]; then
  rm -f -- "${decision_file}"
  blocked "BLOCKED_POLICY" "this decision was already spent; one ALLOW authorizes one operation"
fi
cp -- "${decision_file}" "${spent}"
# BSD chmod does not accept `--`; the path is one we constructed from a digest.
chmod 0444 "${spent}"
rm -f -- "${decision_file}"

cat "${spent}"
