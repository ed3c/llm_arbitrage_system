#!/usr/bin/env bash
# Deterministic Git Town stand-in for the fail-closed canaries (issue #19).
#
# Git Town is not admitted on any host (#15), and a real binary would only ever
# demonstrate the happy path. Every disagreement-producing condition the Worker
# protocol must survive — semantic conflict, silent conflict, editor prompt,
# credential prompt, timeout, orphan process, dirty tree, unexpected ref
# movement, residue — is produced here on demand instead.
#
# Selected by CANARY_BEHAVIOUR. Every invocation is appended to
# CANARY_INVOCATION_LOG so a control can assert which command shapes actually
# reached the tool rather than inferring it from side effects.

set -u

if [ "${1:-}" = "--version" ]; then
  printf 'git-town %s\n' "${CANARY_VERSION:-v24.0.0}"
  exit 0
fi

[ -z "${CANARY_INVOCATION_LOG:-}" ] || printf '%s\n' "$*" >> "${CANARY_INVOCATION_LOG}"

git_dir="$(git rev-parse --absolute-git-dir)"
work_tree="$(git rev-parse --show-toplevel)"

plant_conflict_markers() {
  cat > "${work_tree}/leased.txt" <<'MARKERS'
<<<<<<< HEAD
ours
=======
theirs
>>>>>>> parent
MARKERS
  # A real interrupted merge leaves this behind; the adapter must notice it
  # even when the tool says nothing.
  git rev-parse HEAD > "${git_dir}/MERGE_HEAD"
}

case "${CANARY_BEHAVIOUR:-clean}" in
  clean)
    printf 'branch is up to date\n'
    exit 0
    ;;
  semantic-conflict)
    plant_conflict_markers
    printf 'CONFLICT (content): Merge conflict in leased.txt\n' >&2
    exit 1
    ;;
  silent-conflict)
    # Exits zero and says nothing while leaving the tree unmergeable. Tool exit
    # status alone must never be the repository result.
    plant_conflict_markers
    exit 0
    ;;
  editor-prompt)
    printf 'hint: Waiting for your editor to close the file...\n' >&2
    exit 1
    ;;
  credential-prompt)
    printf "Username for 'https://github.com': " >&2
    exit 1
    ;;
  hang)
    sleep 120
    exit 0
    ;;
  orphan)
    # A grandchild that outlives the direct child unless the whole session is
    # reaped. It writes its pid so a control can look for a survivor.
    ( sleep 120 ) &
    printf '%s\n' "$!" > "${CANARY_ORPHAN_PID_FILE:-/dev/null}"
    sleep 120
    exit 0
    ;;
  dirty)
    printf 'uncommitted\n' >> "${work_tree}/leased.txt"
    exit 0
    ;;
  ref-move)
    git branch -f main HEAD
    exit 0
    ;;
  residue)
    printf 'left behind\n' > "${work_tree}/canary-residue.tmp"
    exit 0
    ;;
  *)
    printf 'unknown canary behaviour: %s\n' "${CANARY_BEHAVIOUR:-}" >&2
    exit 9
    ;;
esac
