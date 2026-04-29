from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


# Module-level log destination for reliability runs. Tests may monkeypatch this.
RELIABILITY_LOG_PATH: Path = Path("logs") / "pawpal_runs.jsonl"

logger = logging.getLogger("pawpal")
if not logger.handlers:
	logger.addHandler(logging.NullHandler())


@dataclass
class Owner:
	name: str
	available_minutes: int
	preferences: dict[str, Any] = field(default_factory=dict)
	pets: list[Pet] = field(default_factory=list)
	reliability_min_score: float = 0.6

	def __post_init__(self) -> None:
		"""Validate owner initialization values."""
		if self.available_minutes < 0:
			raise ValueError("available_minutes must be >= 0")

	def set_available_time(self, minutes: int) -> None:
		"""Set the owner's available time budget in minutes."""
		if minutes < 0:
			raise ValueError("minutes must be >= 0")
		self.available_minutes = minutes

	def update_preferences(self, preferences: dict[str, Any]) -> None:
		"""Merge new preference values into the owner's preferences."""
		self.preferences.update(preferences)

	def add_pet(self, pet: Pet) -> None:
		"""Register a pet with this owner if not already present."""
		if pet not in self.pets:
			self.pets.append(pet)

	def remove_pet(self, pet: Pet) -> None:
		"""Remove a pet from this owner's registry."""
		if pet in self.pets:
			self.pets.remove(pet)

	def get_all_tasks(self) -> list[Task]:
		"""Return a flattened list of tasks across all owned pets."""
		all_tasks: list[Task] = []
		for pet in self.pets:
			all_tasks.extend(pet.get_tasks())
		return all_tasks


@dataclass
class Task:
	title: str
	duration_minutes: int
	priority: Literal["low", "medium", "high"]
	category: str
	frequency: str = "daily"
	due_date: date = field(default_factory=date.today)
	time_of_day: str | None = None
	pet: Pet | None = None
	completed: bool = False

	def __post_init__(self) -> None:
		"""Validate task initialization values."""
		if self.duration_minutes <= 0:
			raise ValueError("duration_minutes must be > 0")

	def mark_complete(self) -> None:
		"""Mark this task complete and create next occurrence for recurring tasks."""
		self.completed = True

		normalized_frequency = self.frequency.strip().lower()
		next_due_date: date | None = None
		if normalized_frequency == "daily":
			next_due_date = date.today() + timedelta(days=1)
		elif normalized_frequency == "weekly":
			next_due_date = date.today() + timedelta(days=7)

		if next_due_date is not None and self.pet is not None:
			next_task = Task(
				title=self.title,
				duration_minutes=self.duration_minutes,
				priority=self.priority,
				category=self.category,
				frequency=self.frequency,
				due_date=next_due_date,
				time_of_day=self.time_of_day,
			)
			self.pet.add_task(next_task)

	def to_dict(self) -> dict[str, Any]:
		"""Serialize this task into a dictionary representation."""
		return {
			"title": self.title,
			"duration_minutes": self.duration_minutes,
			"priority": self.priority,
			"category": self.category,
			"frequency": self.frequency,
			"due_date": self.due_date.isoformat(),
			"time_of_day": self.time_of_day,
			"pet": self.pet.name if self.pet else None,
			"completed": self.completed,
		}


@dataclass
class Pet:
	name: str
	species: str
	age: int
	owner: Owner
	tasks: list[Task] = field(default_factory=list)

	def __post_init__(self) -> None:
		"""Validate pet initialization values and register with owner."""
		if self.age < 0:
			raise ValueError("age must be >= 0")
		self.owner.add_pet(self)

	def get_tasks(self) -> list[Task]:
		"""Return a copy of this pet's task list."""
		return list(self.tasks)

	def add_task(self, task: Task) -> None:
		"""Attach a task to this pet and set task ownership."""
		task.pet = self
		if task not in self.tasks:
			self.tasks.append(task)

	def remove_task(self, task: Task) -> None:
		"""Detach a task from this pet and clear task ownership."""
		if task in self.tasks:
			self.tasks.remove(task)
		if task.pet is self:
			task.pet = None


@dataclass
class Scheduler:
	pet: Pet
	# Keep these optional in the skeleton so implementations can default to pet/owner state.
	tasks: list[Task] | None = None
	time_budget: int | None = None

	def detect_time_conflicts(self) -> list[str]:
		"""Return warning messages for tasks sharing the same scheduled time.

		This lightweight strategy reports collisions and does not raise exceptions.
		"""
		conflicts: list[str] = []
		tasks_by_time: dict[str, list[Task]] = {}

		for task in self.filter_tasks():
			if not task.time_of_day:
				continue
			tasks_by_time.setdefault(task.time_of_day, []).append(task)

		for time_of_day in sorted(tasks_by_time):
			tasks_at_time = tasks_by_time[time_of_day]
			if len(tasks_at_time) < 2:
				continue

			task_labels: list[str] = []
			for task in tasks_at_time:
				pet_name = task.pet.name if task.pet is not None else "Unknown pet"
				task_labels.append(f"{pet_name}: {task.title}")

			conflicts.append(
				f"Warning: time conflict at {time_of_day} for {', '.join(task_labels)}."
			)

		return conflicts

	def filter_tasks(self, completed: bool | None = None, pet_name: str | None = None) -> list[Task]:
		"""Filter tasks by completion status and/or pet name.

		- If ``completed`` is None, both complete and incomplete tasks are returned.
		- If ``pet_name`` is provided, matching is case-insensitive.
		"""
		if self.tasks is not None:
			tasks = list(self.tasks)
		elif self.pet.owner.pets:
			tasks = self.pet.owner.get_all_tasks()
		else:
			tasks = self.pet.get_tasks()

		if completed is not None:
			tasks = [task for task in tasks if task.completed is completed]

		if pet_name is not None:
			normalized_pet_name = pet_name.strip().lower()
			tasks = [
				task
				for task in tasks
				if task.pet is not None and task.pet.name.lower() == normalized_pet_name
			]

		return tasks

	def _candidate_tasks(self) -> list[Task]:
		"""Collect incomplete tasks relevant to this scheduling context."""
		return self.filter_tasks(completed=False)

	def _budget(self) -> int:
		"""Return a non-negative time budget for scheduling."""
		budget = self.time_budget if self.time_budget is not None else self.pet.owner.available_minutes
		return max(0, budget)

	def filter_by_time(self) -> list[Task]:
		"""Filter candidate tasks to those that fit the total budget."""
		budget = self._budget()
		return [task for task in self._candidate_tasks() if task.duration_minutes <= budget]

	def sort_by_priority(self) -> list[Task]:
		"""Sort schedulable tasks by priority and tie-breaker rules."""
		priority_rank = {"high": 3, "medium": 2, "low": 1}
		return sorted(
			self.filter_by_time(),
			key=lambda task: (-priority_rank[task.priority], task.duration_minutes, task.title.lower()),
		)

	def sort_by_time(self) -> list[Task]:
		"""Sort schedulable tasks by HH:MM time strings.

		Tasks without a set time are placed at the end.
		"""
		return sorted(
			self.filter_by_time(),
			key=lambda task: task.time_of_day if task.time_of_day else "99:99",
		)

	def build_plan(self) -> dict[str, Any]:
		"""Build a schedule plan that fits tasks into the available budget."""
		budget = self._budget()
		scheduled: list[Task] = []
		skipped: list[dict[str, Any]] = []
		time_used = 0

		for task in self.sort_by_priority():
			if time_used + task.duration_minutes <= budget:
				scheduled.append(task)
				time_used += task.duration_minutes
			else:
				skipped.append(
					{
						"task": task.to_dict(),
						"reason": "Not enough remaining time budget",
					}
				)

		return {
			"scheduled_tasks": [task.to_dict() for task in scheduled],
			"skipped_tasks": skipped,
			"total_time_used": time_used,
			"remaining_minutes": budget - time_used,
			"time_budget": budget,
		}

	def explain_plan(self) -> dict[str, Any]:
		"""Return the generated plan along with human-readable reasoning."""
		plan = self.build_plan()
		explanation: list[str] = []

		for task in plan["scheduled_tasks"]:
			explanation.append(
				f"Included '{task['title']}' ({task['duration_minutes']} min) because it fits the budget and has {task['priority']} priority."
			)

		for skipped in plan["skipped_tasks"]:
			task = skipped["task"]
			explanation.append(
				f"Skipped '{task['title']}' ({task['duration_minutes']} min): {skipped['reason']}."
			)

		return {
			"plan": plan,
			"reasoning": explanation,
		}

	# ------------------------------------------------------------------
	# Reliability extension
	# ------------------------------------------------------------------

	def build_reliable_plan(self) -> dict[str, Any]:
		"""Build a plan, score its reliability, apply guardrails, and log the run.

		Returns a dict with keys: ``plan``, ``conflicts``, ``reliability``,
		and ``reasoning``. The reliability report can change the plan when the
		score is below the owner's minimum threshold.
		"""
		candidate_tasks = self._candidate_tasks()
		conflicts = self.detect_time_conflicts()
		plan = self.build_plan()

		scorer = ReliabilityScorer()
		report = scorer.evaluate(plan, conflicts, candidate_tasks)

		min_score = getattr(self.pet.owner, "reliability_min_score", 0.6)
		if report.score < min_score:
			plan, report = self._apply_reliability_guardrails(
				plan, report, conflicts, candidate_tasks, min_score
			)

		reasoning = self._explain_with_reliability(plan, report)

		try:
			self.log_run(report, plan)
		except OSError as exc:
			warning = f"Warning: failed to write reliability log ({exc})."
			report.signals.append(warning)
			reasoning.append(warning)
			logger.warning("Reliability log write failed: %s", exc)

		return {
			"plan": plan,
			"conflicts": conflicts,
			"reliability": report.to_dict(),
			"reasoning": reasoning,
		}

	def _apply_reliability_guardrails(
		self,
		plan: dict[str, Any],
		report: "ReliabilityReport",
		conflicts: list[str],
		candidate_tasks: list[Task],
		min_score: float,
	) -> tuple[dict[str, Any], "ReliabilityReport"]:
		"""Adjust a low-confidence plan to raise its reliability score.

		Strategies (in order):
			1. Reorder scheduled tasks by time-of-day when conflicts exist.
			2. Iteratively drop the lowest-priority scheduled task until the
			   score meets ``min_score`` or only high-priority tasks remain.
		"""
		actions: list[str] = []
		scorer = ReliabilityScorer()

		if conflicts:
			plan["scheduled_tasks"].sort(
				key=lambda task: task.get("time_of_day") or "99:99"
			)
			actions.append(
				"Reordered scheduled tasks by time-of-day to mitigate conflicts."
			)

		priority_rank = {"low": 0, "medium": 1, "high": 2}
		current_report = report
		while True:
			current_report = scorer.evaluate(plan, conflicts, candidate_tasks)
			if current_report.score >= min_score:
				break

			droppable = [
				task for task in plan["scheduled_tasks"] if task["priority"] != "high"
			]
			if not droppable:
				break

			droppable.sort(
				key=lambda task: (
					priority_rank[task["priority"]],
					-task["duration_minutes"],
				)
			)
			victim = droppable[0]
			plan["scheduled_tasks"].remove(victim)
			plan["skipped_tasks"].append(
				{
					"task": victim,
					"reason": "Dropped by reliability guardrail (low confidence).",
				}
			)
			plan["total_time_used"] -= victim["duration_minutes"]
			plan["remaining_minutes"] = plan["time_budget"] - plan["total_time_used"]
			actions.append(
				f"Dropped low-priority task '{victim['title']}' to raise reliability score."
			)

		current_report.actions = actions
		return plan, current_report

	def log_run(self, report: "ReliabilityReport", plan: dict[str, Any]) -> None:
		"""Append a JSON line describing this scheduling run to the log file."""
		log_path = RELIABILITY_LOG_PATH
		log_path.parent.mkdir(parents=True, exist_ok=True)

		entry = {
			"timestamp": datetime.now().isoformat(),
			"owner": self.pet.owner.name,
			"pet": self.pet.name,
			"reliability": report.to_dict(),
			"scheduled_count": len(plan.get("scheduled_tasks", [])),
			"skipped_count": len(plan.get("skipped_tasks", [])),
			"time_used": plan.get("total_time_used", 0),
			"time_budget": plan.get("time_budget", 0),
		}

		with log_path.open("a", encoding="utf-8") as log_file:
			log_file.write(json.dumps(entry) + "\n")

	def _explain_with_reliability(
		self, plan: dict[str, Any], report: "ReliabilityReport"
	) -> list[str]:
		"""Build human-readable reasoning that includes reliability context."""
		reasoning: list[str] = []

		for task in plan["scheduled_tasks"]:
			reasoning.append(
				f"Included '{task['title']}' ({task['duration_minutes']} min, "
				f"{task['priority']} priority)."
			)

		for skipped in plan["skipped_tasks"]:
			task = skipped["task"]
			reasoning.append(
				f"Skipped '{task['title']}' ({task['duration_minutes']} min): "
				f"{skipped['reason']}"
			)

		reasoning.append(
			f"Reliability: {report.status.upper()} "
			f"(score {report.score:.2f})."
		)
		for signal in report.signals:
			reasoning.append(f"Signal: {signal}.")
		for action in report.actions:
			reasoning.append(f"Action: {action}")

		return reasoning


@dataclass
class ReliabilityReport:
	"""Structured reliability assessment for a scheduling run."""

	score: float
	status: Literal["high", "medium", "low"]
	signals: list[str] = field(default_factory=list)
	actions: list[str] = field(default_factory=list)
	generated_at: datetime = field(default_factory=datetime.now)

	def to_dict(self) -> dict[str, Any]:
		"""Serialize this report into a JSON-friendly dict."""
		return {
			"score": round(self.score, 3),
			"status": self.status,
			"signals": list(self.signals),
			"actions": list(self.actions),
			"generated_at": self.generated_at.isoformat(),
		}


class ReliabilityScorer:
	"""Score scheduling reliability using weighted signal penalties."""

	HIGH_THRESHOLD = 0.8
	MEDIUM_THRESHOLD = 0.6

	def evaluate(
		self,
		plan: dict[str, Any],
		conflicts: list[str],
		tasks: list[Task],
	) -> ReliabilityReport:
		"""Return a ReliabilityReport for the given plan inputs."""
		breakdown = self.score_signals(plan, conflicts, tasks)
		raw_score = 1.0 - sum(breakdown.values())
		score = max(0.0, min(1.0, raw_score))
		signals = [name for name, weight in breakdown.items() if weight > 0]
		return ReliabilityReport(
			score=score,
			status=self.status_from_score(score),
			signals=signals,
		)

	def score_signals(
		self,
		plan: dict[str, Any],
		conflicts: list[str],
		tasks: list[Task],
	) -> dict[str, float]:
		"""Return a per-signal weight breakdown used to compute the score."""
		breakdown: dict[str, float] = {}

		if conflicts:
			breakdown[f"{len(conflicts)} time conflict(s) detected"] = (
				0.15 * len(conflicts)
			)

		skipped_high = [
			item
			for item in plan.get("skipped_tasks", [])
			if item["task"]["priority"] == "high"
		]
		if skipped_high:
			breakdown[f"{len(skipped_high)} high-priority task(s) skipped"] = (
				0.10 * len(skipped_high)
			)

		if (
			plan.get("time_budget", 0) > 0
			and plan.get("remaining_minutes", 0) < 10
		):
			breakdown["Tight remaining time budget (<10 min)"] = 0.05

		if tasks:
			missing_time = sum(1 for task in tasks if not task.time_of_day)
			if missing_time / len(tasks) > 0.5:
				breakdown["More than half of tasks have no time-of-day"] = 0.05

		return breakdown

	def status_from_score(self, score: float) -> Literal["high", "medium", "low"]:
		"""Map a numeric score to a coarse high/medium/low status."""
		if score >= self.HIGH_THRESHOLD:
			return "high"
		if score >= self.MEDIUM_THRESHOLD:
			return "medium"
		return "low"
