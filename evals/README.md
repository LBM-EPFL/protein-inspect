# Eval runbook

Quickstart for running the protein-inspect eval over a weekend.

## Pre-flight (do this once before launching)

```bash
# 1. Make sure you're logged into Claude Code (Max plan auth)
claude --version    # should print without auth errors

# 2. Make sure PyMOL is running with the claudemol plugin
open /Applications/PyMOL.app   # leaves PyMOL running; plugin auto-loads from ~/.pymolrc
/Users/singer/.claudemol/bin/claudemol status   # should show "Socket connection: OK"

# 3. Verify dependencies
cd /Users/singer/claude_mol_test
uv sync --extra dev
```

## Smoke tests (recommended before the full run)

```bash
# 5 minutes — condition B (YAML only, no PyMOL needed) on 1 protein
uv run python evals/run_eval.py --only 1ubq --conditions B --skip-render

# 10 minutes — full pipeline on 1 protein, all 4 conditions (needs PyMOL)
uv run python evals/run_eval.py --only 2zju --conditions ABCD
```

Check `evals/runs/<latest>/results.md` — should show scores.

## Full weekend run

```bash
# All 30 proteins × 4 conditions = 120 subject + 240 judge = 360 Claude calls
uv run python evals/run_eval.py 2>&1 | tee evals/runs/full_$(date +%Y%m%d).log
```

Expected wall time: **8–15 hours active**, longer if rate-limited. The script saves state after every call and resumes on interruption.

## Resume after interruption

```bash
# If interrupted (Ctrl+C, crash, rate-limit exhaustion):
uv run python evals/run_eval.py --run-dir evals/runs/<that-same-dir>
# State.json drives resume; already-scored items are skipped.
```

## Useful flags

| Flag | Purpose |
|---|---|
| `--only 1ubq,2zju,5cha` | Run only specific PDBs |
| `--conditions BC` | Skip A and D; just compare YAML-only vs YAML+images |
| `--skip-render` | Skip PyMOL rendering (condition C will fail gracefully) |
| `--limit 5` | Cap at first N proteins (for debugging) |
| `--subject-model claude-sonnet-4-6` | Switch model under test |
| `--judge-model claude-haiku-4-5-20251001` | Cheaper / faster judge |
| `--run-dir <path>` | Resume an existing run |
| `--quiet` | Suppress info logs |

## Rate-limit behavior

Max 5x at Opus 4.7: roughly 30–50 messages / 5-hour window. The driver:

- Detects 429 / "usage limit" in stderr
- Sleeps with exponential backoff (60s → 90s → ... capped at 30 min)
- Up to 20 retries per call
- Saves state between every call (resume-friendly)

If you hit the cap, the script will pause and resume automatically. You can let it run unattended.

## Output layout

```
evals/runs/<date>_<git-sha>/
├── state.json                  # resume marker
├── eval.log                    # full log
├── cache/<sha16>.json          # raw Claude responses, keyed by prompt hash
├── responses/<pdb>_<cond>.txt  # subject responses (readable)
├── extracts/<pdb>_<cond>.json  # judge extraction
├── scores/<pdb>_<cond>.json    # judge scoring
└── results.md                  # human-readable table — the final deliverable
```

`results.md` is what goes in the marketplace submission README.

## When you come back Monday

```bash
# See where it got to
cat evals/runs/<latest>/results.md
cat evals/runs/<latest>/eval.log | tail -30

# Spot-check a few high-leverage entries
cat evals/runs/<latest>/responses/2zju_C.txt    # AChBP with images
cat evals/runs/<latest>/scores/2zju_C.json
cat evals/runs/<latest>/responses/af_q9un36_B.txt   # NDRG2 pseudo-enzyme trap
cat evals/runs/<latest>/scores/af_q9un36_B.json
```

If anything looks off, ping me — I'll adjust the rubric or rerun specific items.

## Cost (informational)

This uses your Max plan auth, NOT API billing. The cost numbers shown in `cache/*.json` are what the calls WOULD have cost on API billing — they're informational. Your actual cost: **whatever fraction of Max plan rate-limit you consume.**

Per-call API equivalent: ~$0.10–0.20 with Opus 4.7. Total full run equivalent: **~$30–60 if billed via API**. You're paying $0 in marginal cost; you're spending time-on-rate-limit instead.

## Verifying the eval is honest

After the run completes, spot-check 3–5 entries manually:

1. Read `evals/runs/<run>/responses/<pdb>_<cond>.txt`
2. Read `evals/runs/<run>/scores/<pdb>_<cond>.json`
3. Confirm the judge's rationales are sensible

If the judge looks suspicious (rationales contradict scores, or fails to apply negative constraints), tell me and I'll iterate on the judge prompts.
