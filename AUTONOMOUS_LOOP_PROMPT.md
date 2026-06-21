# Autonomous Loop Prompt — Quant Trading System

You are continuing development of this quant trading system, working autonomously one iteration at a
time. Repo: this directory. Git remote: github.com/zmanupnow777/Quantitative-Bot, branch `main`.

## End goal
A rigorously validated, risk-managed trading bot that has proven itself over **30+ days of PAPER
trading** before any real money is ever considered — and that explains its decisions in plain
English. Success is an honest answer to "does this have an edge?", not a profit target. If the
evidence says a strategy has no edge, say so.

## Start every iteration by reading current state (do NOT skip)
1. `git log --oneline -15` and `git status`.
2. `docs/superpowers/specs/` and `docs/superpowers/plans/` (newest first) — find the latest spec/plan
   and whether it has been implemented (check git log for its feature commits).
3. `.superpowers/sdd/progress.md` if present (an in-flight subagent run to resume).
4. `claude_code_roadmap.md` and the latest `*_HANDOFF.md` for the roadmap and where things stand.

## Then advance ONE coherent unit of work, in this priority order
A. In-flight subagent run (ledger exists, tasks unfinished) → resume it; never re-do completed tasks.
B. A spec exists with no implementation plan → write the plan (writing-plans skill).
C. A plan exists, not yet executed → execute via subagent-driven-development: TDD, fresh subagent per
   task, spec+quality review after each, final whole-branch review on the most capable model. Work on
   a feature branch; when green, merge to `main` and push.
D. Everything merged → advance the roadmap. Current priority order:
   1. Implement the ATR position-sizing rework (spec: `docs/superpowers/specs/2026-06-21-position-sizing-design.md`).
   2. Re-run the optimizer + backtests; review the new return AND drawdown profile.
   3. Start / continue the paper (or sim) run; log results to `logs/`.
   4. Weekly: compare paper results vs backtest expectations; flag divergence.
   5. Research and refine strategies; keep the dashboard working.

## Always
- Keep the test suite green (`./.venv/Scripts/python.exe -m pytest tests -q`). Commit in small units.
- Address EVERY Critical/Important finding AND every actionable Minor finding from reviews — the human
  wants thoroughness, not deferral.
- Push to `origin/main` when a unit of work is merged.
- End each iteration by updating the ledger/handoff so the next iteration (or the human) resumes
  cleanly.

## HARD GUARDRAILS — never violate
- **PAPER / SIM / BACKTEST ONLY.** Never start live/real-money trading, never pass `--confirm-live`,
  never point a broker at a live endpoint, never move real funds. Going live is a **human-only**
  decision the user must perform themselves. If a task seems to require live trading, STOP and leave a
  note instead.
- Use the superpowers skills: brainstorming before any new feature/behavior change, writing-plans,
  subagent-driven-development, the review skills, finishing-a-development-branch.
- You may approve your own design ONLY for work already agreed on the roadmap or in an approved spec.
  If a genuine **product decision** arises that the user hasn't settled, STOP and leave the question
  for them — do not guess.
- Never fabricate results. Report real test/backtest output verbatim.

## When to stop and wait for the human
If the only way forward needs a live-trading action, a real-money decision, or an unsettled product
choice — summarize the open decision(s) clearly and stop. Otherwise, keep advancing.
