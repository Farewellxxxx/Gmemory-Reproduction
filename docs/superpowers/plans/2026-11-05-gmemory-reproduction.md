# GMemory Reproduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Run real PDDL + AutoGen + GMemory and matched no-memory experiments with inspectable traces and Chinese teaching materials.

**Architecture:** Preserve the upstream repository and memory algorithm. Add a bounded reproduction entrypoint, instrumented model adapter, isolated outputs, and portable installation instructions. Compatibility patches remain explicit.

**Tech Stack:** Python 3.12, upstream PDDL/Gym, SentenceTransformers, Chroma, OpenAI-compatible ChatAnywhere API, pytest, Git.

**Spec:** `EXECUTION_PROMPT_zh.md`

## Global Constraints
- Upstream `7b581c51d993bd600df14691d101d7e601040cc6`; model `gpt-4o-mini`; provider default group.
- Maximum 50 CA and 6 hours; no secret in logs/Git; no uncontrolled retries.
- Same tasks/order/action budget for both arms; separate state directories; preserve insight thresholds 5/5/20.
- Public repository push authorized; no claim of full paper replication from small experiments.

## Review Focus
- API timeouts/usage omissions must stop safely, without silently treating empty answers as scientific outcomes.
- Restart must retain the global spend ledger and avoid overwriting prior experiment state.
- Environment reset and task truncation must not reuse prior task state or run an entire benchmark accidentally.
- Role projection and memory persistence must be demonstrated from real completed episodes, with no future-task leakage.
- Export and history scanning must reject secret-bearing artifacts and label inherited upstream logs separately.

### Task 1: Reproducible environment and upstream compatibility
**Files:** `.gitignore`, `requirements-repro.txt`, `tests/test_pddl_runtime.py`, minimal files under `tasks/envs/` if required.
**Interfaces:** Produces real `PDDLEnv.set_env(task)` and `step(action)` behavior and an isolated Python interpreter.
- [x] Inspect imports, data and environment action/reset semantics; run original smoke check and record failures before patching.
- [x] Install the PDDL-relevant pinned dependency subset; keep unrelated benchmark dependencies optional.
- [x] Add regression tests for observed environment/loading defects, verify failure, implement minimal compatibility fix, rerun.
- [x] Verify original task loading and real state transition; commit installation/compatibility changes.

### Task 2: Bounded API and experiment runner
**Files:** `repro/`, `tests/test_runtime.py`, `mas/llm.py`, `.env.example`, `configs/reproduction.json`.
**Interfaces:** Produces `python -m repro.run` with explicit task count, arm, output directory and shared ledger; preserves `GPTChat.__call__` signature.
- [x] Write tests for secret-free imports, budget exhaustion, API failure, usage logging, task selection and existing-output rejection; observe failures.
- [x] Implement guarded calls, request/response traces and a deterministic task manifest using existing MAS/environment classes.
- [x] Run all reproduction tests and a paid 16-token connectivity probe; persist sanitized provider metadata.
- [x] Commit the runnable infrastructure.

### Task 3: Real paired experiments and memory trace
**Files:** `configs/reproduction.json`, local `runs/`, public `artifacts/first-run/`, `repro/analyze.py`.
**Interfaces:** Consumes bounded runner; produces per-task results, call ledger, selected trace and memory snapshots.
- [x] Freeze task selection before outcomes; verify identical manifests across arms and fresh independent memory directories.
- [x] Run GMemory and no-memory arms within shared total budget; checkpoint completed episodes.
- [x] Verify actual extraction, insight formation, retrieval, projector and persistence/reload; report any missing path honestly.
- [x] Analyze results, token/time/cost and failure modes; export sanitized reproducible evidence and commit.

### Task 4: Teaching, review and publication
**Files:** `README_zh.md`, `REPRODUCE_zh.md`, `PAPER_TO_CODE_zh.md`, `WALKTHROUGH_zh.md`, `REPORT_zh.md`, `RUNBOOK.md`.
**Interfaces:** Consumes real artifacts; produces a clean clone-to-run guide and a trace-backed teaching narrative.
- [x] Explain each execution step, algorithm-to-code map, real cross-task example and limitations in Chinese.
- [ ] Verify documented commands, test suite, artifact counts/costs, secret scanning and Git status.
- [ ] Request a fresh whole-branch review; address material findings with regression checks.
- [ ] Push approved output to `Farewellxxxx/Gmemory-Reproduction` and verify remote commit.
