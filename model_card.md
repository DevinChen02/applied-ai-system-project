# Model Card — PawPal+

> A structured reflection on what PawPal+ is, what it is *not*, how it makes decisions, and where it can fail. This card is meant to be read alongside [README.md](README.md) and [reflection.md](reflection.md).

## 1. Model / System Details

- **Name:** PawPal+ — Pet Care Planning Assistant
- **Version:** 1.0 (Module 2 final, with Reliability Extension)
- **Owner / Author:** Devin (course project, Applied AI Systems)
- **Date:** April 2026
- **Type:** Deterministic, rule-based planning system with a weighted-signal reliability scorer. **No LLM is in the decision loop.**
- **Primary entry points:**
  - UI: [app.py](app.py) (Streamlit) → calls `Scheduler.build_reliable_plan()`
  - CLI: [main.py](main.py)
  - Core logic: [pawpal_system.py](pawpal_system.py)
- **Stack:** Python 3, Streamlit, `dataclasses`, `logging`, `pytest`. Pinned in [requirements.txt](requirements.txt).
- **License / availability:** Course project, intended for portfolio and educational use.

## 2. Intended Use

- **Primary use case:** Help a busy pet owner turn a list of pet care tasks (walks, feeding, meds, grooming, enrichment) into a realistic, prioritized daily plan that fits their available time budget, with explainable reasoning and a reliability score.
- **Intended users:** Individual pet owners, especially multi-pet households; students/instructors evaluating an applied AI systems project.
- **Intended deployment context:** Local desktop use via Streamlit. Single-user, single-session, no authentication, no network calls.

### Out-of-scope use

- **Not** a veterinary, medical, dietary, or behavioral advice tool. The system has no knowledge of medication interactions, species-specific health needs, or emergencies.
- **Not** a calendar/notification system — it does not send reminders, sync to external calendars, or persist state between sessions.
- **Not** suitable for commercial scheduling (kennels, shelters, vet clinics) without significant changes to data model, persistence, and access control.
- **Not** a replacement for owner judgement when the reliability score is low or a guardrail drops a task.

## 3. System Architecture (summary)

For the full diagram, see the **System Diagram** section in [README.md](README.md). At a glance:

`Owner / Pet / Task` (domain) → `Scheduler` (filter → sort → conflict-check → `build_plan`) → `ReliabilityScorer` (weighted signals → `ReliabilityReport`) → guardrails (`reorder by time`, `drop lowest-priority`) → JSONL log (`logs/pawpal_runs.jsonl`) → Streamlit UI → human review.

The reliability layer is **inside** the planning flow, not bolted on after — it can change which tasks end up on the final plan.

## 4. How Decisions Are Made

### 4a. Scheduling (`Scheduler.build_plan`)

1. Filter to incomplete tasks for the focal pet (or all of the owner's pets).
2. Sort by `priority → duration → title`.
3. Greedily pack tasks into `owner.available_minutes` until the budget is exhausted.
4. `detect_time_conflicts()` flags tasks sharing a `time_of_day` as **warnings**, not exceptions.
5. `explain_plan()` returns a per-task reason string ("fits the budget and is high priority", "Not enough remaining time budget", etc.).

### 4b. Reliability scoring (`ReliabilityScorer.evaluate`)

Score starts at `1.0` and is reduced by weighted penalties:

| Signal | Penalty |
| --- | --- |
| Each time-of-day conflict | −0.15 |
| Each high-priority task skipped | −0.10 |
| Remaining minutes < 10 | −0.05 |
| More than half of tasks have no `time_of_day` | −0.05 |

Status mapping: `>= 0.8` **high**, `0.6–0.79` **medium**, `< 0.6` **low**.

### 4c. Guardrails (`Scheduler._apply_reliability_guardrails`)

If `score < owner.reliability_min_score`:
- Reorder scheduled tasks by `time_of_day` to mitigate conflicts.
- Iteratively drop the lowest-priority scheduled task until the score recovers or only high-priority tasks remain.

Every action is recorded in `ReliabilityReport.actions` and surfaced in the UI.

## 5. Training Data

**None.** PawPal+ is not a learned model. There are no training datasets, no fine-tuning, and no learned parameters. All thresholds, weights, and rules were chosen by the author based on the project's design constraints. The only "data" the system sees is the owner/pet/task input the user types in.

## 6. Evaluation

- **Automated tests:** 20 / 20 pass via `python -m pytest` ([tests/test_pawpal.py](tests/test_pawpal.py)). Coverage spans scheduling, sorting, conflict detection, recurrence, signal penalties, status mapping, guardrail drop/reorder, and JSONL log writes (using `tmp_path` + `monkeypatch` so tests never touch the real log).
- **Reliability scenarios:** Across 5 representative scheduling scenarios, confidence scores averaged **0.90** (range **0.80 – 1.00**). The lowest score (0.80) came from a multi-pet 08:00 conflict + tight-budget case; the guardrail correctly dropped the lowest-priority task to recover the score.
- **Human evaluation:** The Streamlit UI surfaces the scheduled plan, skipped tasks, reliability score, signals, and guardrail actions so a human can audit every change before acting on it.
- **Logging:** Every run is appended as a JSON line to `logs/pawpal_runs.jsonl` for after-the-fact review.

## 7. Reflection

### Limitations and biases in the system

PawPal+ has real limitations baked into its design choices. The scheduler is **greedy and priority-first**, which means a single high-priority task can crowd out several useful low-priority ones — owners who under-rate enrichment or grooming as "low" will see those tasks repeatedly skipped, reinforcing their own labeling bias. The reliability scorer uses **fixed, hand-picked weights** (−0.15 per conflict, −0.10 per skipped high-priority task, etc.); those numbers reflect *my* intuition about what makes a plan trustworthy, not an empirical study, so the score is opinionated rather than objective. The system also assumes the owner accurately knows their `available_minutes` and each task's `duration_minutes` — garbage in, confidently-scored garbage out. Finally, the model is **species-agnostic in its logic** but the example data and defaults skew toward common pets (dogs, cats); owners of reptiles, birds, or exotics may find the priority/category vocabulary doesn't fit their care routines.

### Potential misuse and prevention

The most realistic misuse is **over-trusting the plan** — an owner could treat the schedule as medical advice ("the AI didn't include the medication, so I'll skip it today") instead of as a planning aid. To mitigate this, every plan ships with an explicit reasoning trace (`explain_plan()`), the reliability score and signals are surfaced in the UI, and guardrail actions ("Dropped low-priority task X") are logged so the human can always see *what* was changed and *why*. A second risk is **logging sensitive data**: `logs/pawpal_runs.jsonl` includes owner and pet names; if shared, that's a small privacy leak. Prevention is to keep `logs/` local (it's already untracked), document the logging behavior in the README, and avoid putting medical or financial detail into task titles. Finally, the deterministic scorer can't be jailbroken with prompt injection (no LLM in the loop), which is a deliberate safety win over a hypothetical "LLM judge" design.

### What surprised me while testing reliability

The biggest surprise was how often the **guardrail did nothing because the score landed exactly on the threshold**. My first reliability tests passed for the wrong reason — the score was `0.6`, the threshold was `0.6`, so `score < min_score` was false and no guardrail ran. That taught me to design test inputs that land *clearly* on one side of a threshold, and it made me add a strict-mode toggle (0.8) so the guardrail behavior is observable in the UI. I was also surprised that the simplest signal — "remaining budget < 10 minutes" — caught more low-confidence runs than the conflict signal did; tight budgets, not collisions, were the dominant failure mode in my sample scenarios. And monkeypatching `RELIABILITY_LOG_PATH` turned out to be far cleaner than threading a path through every method, which I wouldn't have predicted from the UML.

### Collaboration with AI during this project

I used AI (GitHub Copilot Chat) as a drafting and debugging partner throughout — for class boundary brainstorming, writing the first cut of `ReliabilityScorer`, and shaping pytest fixtures around `tmp_path` + `monkeypatch`.

- **One genuinely helpful suggestion:** when I described the reliability layer in plain English, the AI suggested making `RELIABILITY_LOG_PATH` a **module-level constant** that tests could `monkeypatch`, instead of injecting a log path through `Scheduler.__init__` and every downstream call. That suggestion collapsed a tangle of constructor arguments into one line of test setup (`monkeypatch.setattr(pawpal_system, "RELIABILITY_LOG_PATH", tmp_path / "runs.jsonl")`) and is the reason the reliability tests are short and readable.
- **One flawed suggestion I rejected:** for time-conflict handling, the AI initially proposed **raising an exception** when two tasks shared a `time_of_day`. I rejected that because a daily planner that crashes on a calendar collision is worse than one that warns — the human is the final arbiter of whether 8:00 walk vs. 8:00 feed is actually a problem. I kept conflicts as warning *strings* surfaced through `detect_time_conflicts()` and as a *signal* in the reliability report, which preserves the information without breaking the flow. The lesson: AI defaults to "fail loudly," but UX-facing systems often need "warn visibly and keep going."

## 8. Maintenance

- **Source of truth:** [pawpal_system.py](pawpal_system.py) for logic, [tests/test_pawpal.py](tests/test_pawpal.py) for behavior.
- **How to change a signal weight:** edit the constants in `ReliabilityScorer` and update the corresponding `test_reliability_score_penalizes_*` test in the same commit.
- **How to change the guardrail policy:** edit `Scheduler._apply_reliability_guardrails`; the drop/reorder tests will catch regressions.
- **Logging:** controlled by the module-level constant `RELIABILITY_LOG_PATH`; tests `monkeypatch` it to `tmp_path` so they never touch the real log directory.


