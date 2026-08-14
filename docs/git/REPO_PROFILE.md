# Repository profile — Git Town Stacked PR Worker

```yaml
schema: git-town-stacked-pr-worker/repo-profile/v1

repository:
  identity: ed3c/llm_arbitrage_system
  github_repository_id: 1333262963
  default_branch: main
  perennial_branches:
    - main
  primary_remote: origin
  admitted_remote_urls:
    - https://github.com/ed3c/llm_arbitrage_system.git
    - git@github.com:ed3c/llm_arbitrage_system.git
  credential_in_url: denied
  baseline_subject: 55ecf0e9a91006f563a080661cb6adf650e2439a

canonical_skill:
  owner_repository: ed3c/skills-shared
  skill_path: skills/git-town-stacked-pr-worker
  consumer_local_shadow_copy: denied
  tracked_binding: documentation pointer
  host_runtime_resolution: NOT_EXERCISED

git_town:
  required_version: v24.0.0
  source_repository: git-town/git-town
  immutable_tag_commit: 0f3e55f5a6bae5b319dd713a0606263d0551af66
  release_id: 358702660
  checksums_manifest_sha256: 7532377166cb59dc01c74f86e3a71c54ba9567a461313a5d203a1ea99c571b24
  direct_license: MIT
  license_blob_sha: 4bcd5ec1942737f7976b8bac8534a8ab642ec0e0
  license_text_sha256: eec8a092b92231375231488d27b959e2fa2be80559c97db60c1b0458d3298791
  selected_platform_artifact: git-town_macos_arm_64.tar.gz
  selected_platform_artifact_sha256: 0de42d52bad34316413c9d0ba0052d09d4ba8746930aa2cc6eaa5931562a91b2
  installed_executable_sha256: 9f3807e07a6be79e4637b140deda9dff5d3a89321b8026a2f2e4a04d2f37fa2d
  executable_version_output: Git Town 24.0.0
  acquisition_provenance: immutable_release_358702660_asset_verified_against_pinned_manifest
  sbom_or_transitive_review: ACCEPTED
  required_notices_review: ACCEPTED
  organization_legal_approval: APPROVED
  admission_receipt_sha256: eda73fccce27c0885f82d25ef8f6b2fa82047b075e334b22e03c06bb33e7051d
  admitted_host_platform: darwin_arm64
  live_execution_admitted: true

branch_policy:
  main_strategy: ff-only
  feature_strategy: merge
  prototype_strategy: merge
  new_branch_type: feature
  share_new_branches: no
  push_new_branches: false
  auto_sync: false
  auto_resolve: false
  sync_push: false
  push_hook: false
  sync_tags: false
  sync_upstream: false
  history_rewrite_by_worker: denied
  protected_branch_rewrite: denied

worker:
  task_packet_required: true
  one_worker_per_branch: true
  linked_worktree_required: true
  primary_checkout_mutation: denied
  branch_lease_required: true
  path_lease_required: true
  sibling_path_overlap: denied
  worktree_root_selector: host_llm_arbitrage_worktrees
  lease_root_selector: host_llm_arbitrage_leases
  absolute_host_paths_in_tracked_files: denied
  non_interactive: true
  editor_prompt: denied
  credential_prompt: denied
  pager_prompt: denied
  automatic_stash: denied
  automatic_conflict_resolution: denied
  automatic_continue_skip_undo_ship: denied
  timeout_required: true
  background_max_iterations_required: true
  background_default_push: false

sync:
  dry_run_first: true
  dry_run_command_shape: git town sync --stack --dry-run --non-interactive --no-auto-resolve --no-push
  live_command_shape: git town sync --stack --non-interactive --no-auto-resolve --no-push
  global_scope_without_all_leases: denied
  post_sync_graph_verification: required
  post_sync_current_branch_verification: required
  protected_ref_immutability_verification: required
  allowed_path_diff_verification: required
  exact_head_eval_replay: required

publication:
  worker_publication_enabled: false
  state: NOT_IMPLEMENTED_issue_20
  allowed_future_intents:
    - initial-pr
    - ready-for-review
    - batched-repair
  draft_checkpoint_push: denied
  background_push: denied
  background_pr_ready_transition: denied
  background_workflow_rerun: denied
  local_exact_head_receipt: required
  trusted_github_snapshot: required
  post_push_fetch: required
  post_push_exact_remote_head: required
  post_push_ancestry: required
  merge_authority: denied

receipts:
  tracked_root: receipts/git-town
  implementation_state: NOT_IMPLEMENTED_issue_18
  append_only: true
  task_packet_digest: required
  exact_subject_digest: required
  before_after_graph: required
  command_shape: required
  local_sync_lane: required
  local_verification_lane: required
  publication_decision_lane: required
  remote_publication_lane: required
  remote_ancestry_lane: required
  github_trusted_check_lane: required
  cleanup_lane: required
  rollback_subject: required
  secret_values: denied
  credential_urls: denied
  private_keys: denied
  unbounded_stdout_or_stderr: denied

repository_evals:
  install: python -m pip install -e .[dev]
  quality: make check
  phase3_smoke: make phase3-smoke
  phase4_smoke: make phase4-smoke
  git_town_static_contract: docs/git/EVALS.md
  git_town_live_canary: NOT_EXERCISED_issue_21

path_authority:
  runtime_contracts: src/llm_arbitrage_system/domain
  analytics: src/llm_arbitrage_system/analytics
  paper_runtime: src/llm_arbitrage_system/simulation
  replay_storage: src/llm_arbitrage_system/storage
  reporting: src/llm_arbitrage_system/reporting
  experiments_and_trust: src/llm_arbitrage_system/experiments
  repository_git_policy: docs/git
  harness_and_controls: docs/harness
  future_git_adapter: scripts/git-town
  future_git_receipts: receipts/git-town
  convergence_indexes:
    - README.md
    - docs/git/STACKED_PRS.md

forbidden_data:
  - exchange_or_broker_credentials
  - wallet_or_provenance_private_keys
  - seed_phrases
  - account_identifiers
  - withdrawal_authority
  - environment_secret_values
  - browser_session_exports
  - credential_bearing_urls
  - machine_specific_secret_paths

human_owned:
  - semantic_conflict_resolution
  - git_town_continue_skip_undo_ship
  - legal_or_license_acceptance
  - merge_or_merge_queue_admission
  - branch_protection_or_permission_change
  - billing_recovery
  - secret_or_credential_change
  - release_promotion
  - production_deployment
  - destructive_or_drifted_rollback
```

## Profile interpretation

The profile has no unresolved required placeholder. Logical host selectors are names, not absolute paths; issue #17 must resolve them and prove repository/worktree identity without committing host-specific paths.

`required_version` and upstream release metadata are tracked policy inputs. As of admission receipt `eda73fcc`, the host-selected artifact, its digest, the installed executable digest, the executable output, the SBOM/transitive review, the notices review and the legal approval are all `PASS` for one host — `darwin_arm64`. Every one of the twelve required lanes passed, which is the only condition under which `live_execution_admitted` becomes `true`.

That admission is host-bound. It says nothing about any other machine: a different platform or architecture must run `scripts/git-town/admit.sh` and produce its own receipt.

The publication section remains deliberately disabled. Draft PRs in epic #11 were a trusted-operator bootstrap through GitHub, not proof that a Worker publication gate ran.

## Current adoption matrix

| Assertion | State | Evidence / next owner |
| --- | --- | --- |
| Repository identity and main branch | `PASS` | GitHub repository metadata and baseline subject |
| Shared Skill is referenced, not copied | `PASS` for tracked tree | `AGENTS.md`, `docs/git/README.md` |
| Git Town version/tag/release/checksum manifest pin | `PASS` for static policy | this profile and `GIT_TOWN_ADMISSION.md` |
| Direct license bytes reviewed | `PASS` for direct MIT text only | upstream `LICENSE@v24.0.0` |
| Host executable/artifact digest/version | `PASS` for `darwin_arm64` | receipt `eda73fcc` |
| SBOM/transitive/notices/legal admission | `PASS` | receipt `eda73fcc` |
| Task-packet validator | `MERGED` mechanism | #16, `scripts/git-town/task_packet.py` |
| Linked worktree/lease doctor | `MERGED` mechanism | #17, `scripts/git-town/doctor.sh` |
| Bounded sync and receipts | `MERGED` mechanism | #18, `scripts/git-town/sync.sh` |
| Fail-closed canaries | `MERGED` mechanism | #19, `tests/git-town/test_fail_closed_canaries.py` |
| Publication gate | `MERGED` mechanism | #20, `scripts/git-town/publish.sh` |
| Live adoption canary and Human Admit | `NOT_EXERCISED` | #21 |

A `MERGED` mechanism row means the adapter and its disagreement-producing controls exist and pass in CI. Admission makes a live run *possible*; it does not make one *observed*. The live canary stays `NOT_EXERCISED` until issue #21 runs it.
