from datetime import date, timedelta
import json

import pawpal_system
from pawpal_system import (
	Owner,
	Pet,
	ReliabilityReport,
	ReliabilityScorer,
	Scheduler,
	Task,
)


def test_task_mark_complete_changes_status() -> None:
	task = Task(
		title="Walk",
		duration_minutes=20,
		priority="medium",
		category="exercise",
	)

	assert task.completed is False
	task.mark_complete()
	assert task.completed is True


def test_mark_complete_daily_task_creates_next_occurrence() -> None:
	owner = Owner(name="Alex", available_minutes=60)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	task = Task(
		title="Daily Walk",
		duration_minutes=20,
		priority="medium",
		category="exercise",
		frequency="daily",
	)
	pet.add_task(task)

	task.mark_complete()

	assert len(pet.get_tasks()) == 2
	next_task = [pet_task for pet_task in pet.get_tasks() if pet_task is not task][0]
	assert next_task.completed is False
	assert next_task.frequency == "daily"
	assert next_task.due_date == date.today() + timedelta(days=1)


def test_mark_complete_weekly_task_creates_next_occurrence() -> None:
	owner = Owner(name="Alex", available_minutes=60)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	task = Task(
		title="Weekly Grooming",
		duration_minutes=30,
		priority="low",
		category="hygiene",
		frequency="weekly",
	)
	pet.add_task(task)

	task.mark_complete()

	assert len(pet.get_tasks()) == 2
	next_task = [pet_task for pet_task in pet.get_tasks() if pet_task is not task][0]
	assert next_task.completed is False
	assert next_task.frequency == "weekly"
	assert next_task.due_date == date.today() + timedelta(days=7)


def test_mark_complete_non_recurring_task_does_not_create_next_occurrence() -> None:
	owner = Owner(name="Alex", available_minutes=60)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	task = Task(
		title="One-off Vet Visit",
		duration_minutes=45,
		priority="high",
		category="health",
		frequency="once",
	)
	pet.add_task(task)

	task.mark_complete()

	assert len(pet.get_tasks()) == 1


def test_add_task_increases_pet_task_count() -> None:
	owner = Owner(name="Alex", available_minutes=60)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)

	initial_count = len(pet.get_tasks())
	task = Task(
		title="Feed Dinner",
		duration_minutes=10,
		priority="high",
		category="feeding",
	)

	pet.add_task(task)

	assert len(pet.get_tasks()) == initial_count + 1


def test_scheduler_sort_by_time_orders_hhmm_and_puts_empty_last() -> None:
	owner = Owner(name="Alex", available_minutes=120)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)

	pet.add_task(
		Task(
			title="No Time Task",
			duration_minutes=10,
			priority="low",
			category="general",
			time_of_day=None,
		)
	)
	pet.add_task(
		Task(
			title="Morning Feed",
			duration_minutes=10,
			priority="high",
			category="feeding",
			time_of_day="08:00",
		)
	)
	pet.add_task(
		Task(
			title="Walk",
			duration_minutes=20,
			priority="medium",
			category="exercise",
			time_of_day="07:30",
		)
	)

	scheduler = Scheduler(pet=pet)
	ordered = scheduler.sort_by_time()

	assert [task.title for task in ordered] == ["Walk", "Morning Feed", "No Time Task"]


def test_scheduler_filter_tasks_by_completion_status() -> None:
	owner = Owner(name="Alex", available_minutes=120)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)

	completed_task = Task(
		title="Completed Task",
		duration_minutes=10,
		priority="medium",
		category="general",
	)
	completed_task.mark_complete()
	incomplete_task = Task(
		title="Incomplete Task",
		duration_minutes=15,
		priority="high",
		category="general",
	)

	pet.add_task(completed_task)
	pet.add_task(incomplete_task)

	scheduler = Scheduler(pet=pet)

	assert [task.title for task in scheduler.filter_tasks(completed=True)] == ["Completed Task"]
	assert [task.title for task in scheduler.filter_tasks(completed=False)] == ["Incomplete Task"]


def test_scheduler_filter_tasks_by_pet_name_case_insensitive() -> None:
	owner = Owner(name="Alex", available_minutes=120)
	pet1 = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	pet2 = Pet(name="Mochi", species="Cat", age=2, owner=owner)

	pet1.add_task(
		Task(
			title="Walk Buddy",
			duration_minutes=20,
			priority="high",
			category="exercise",
		)
	)
	pet2.add_task(
		Task(
			title="Feed Mochi",
			duration_minutes=10,
			priority="high",
			category="feeding",
		)
	)

	scheduler = Scheduler(pet=pet1)
	filtered = scheduler.filter_tasks(pet_name="mochi")

	assert [task.title for task in filtered] == ["Feed Mochi"]


def test_scheduler_filter_tasks_combines_completion_and_pet_name() -> None:
	owner = Owner(name="Alex", available_minutes=120)
	pet1 = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	pet2 = Pet(name="Mochi", species="Cat", age=2, owner=owner)

	buddys_task = Task(
		title="Buddy Walk",
		duration_minutes=15,
		priority="medium",
		category="exercise",
	)
	completed_mochi_task = Task(
		title="Mochi Meds",
		duration_minutes=5,
		priority="high",
		category="medication",
	)
	completed_mochi_task.mark_complete()
	incomplete_mochi_task = Task(
		title="Mochi Play",
		duration_minutes=10,
		priority="low",
		category="enrichment",
	)

	pet1.add_task(buddys_task)
	pet2.add_task(completed_mochi_task)
	pet2.add_task(incomplete_mochi_task)

	scheduler = Scheduler(pet=pet1)
	filtered = scheduler.filter_tasks(completed=False, pet_name="Mochi")

	assert [task.title for task in filtered] == ["Mochi Play"]


def test_scheduler_detect_time_conflicts_returns_warning_messages() -> None:
	owner = Owner(name="Alex", available_minutes=120)
	pet1 = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	pet2 = Pet(name="Mochi", species="Cat", age=2, owner=owner)

	pet1.add_task(
		Task(
			title="Morning Walk",
			duration_minutes=20,
			priority="high",
			category="exercise",
			time_of_day="08:00",
		)
	)
	pet2.add_task(
		Task(
			title="Feed Breakfast",
			duration_minutes=10,
			priority="high",
			category="feeding",
			time_of_day="08:00",
		)
	)
	pet2.add_task(
		Task(
			title="Litter Scoop",
			duration_minutes=15,
			priority="low",
			category="hygiene",
			time_of_day="09:00",
		)
	)

	scheduler = Scheduler(pet=pet1)
	conflicts = scheduler.detect_time_conflicts()

	assert len(conflicts) == 1
	assert conflicts[0] == (
		"Warning: time conflict at 08:00 for Buddy: Morning Walk, Mochi: Feed Breakfast."
	)


def test_sorting_correctness_returns_tasks_in_chronological_order() -> None:
	owner = Owner(name="Alex", available_minutes=120)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)

	pet.add_task(
		Task(
			title="Late Task",
			duration_minutes=10,
			priority="low",
			category="general",
			time_of_day="11:30",
		)
	)
	pet.add_task(
		Task(
			title="Early Task",
			duration_minutes=15,
			priority="high",
			category="exercise",
			time_of_day="07:15",
		)
	)
	pet.add_task(
		Task(
			title="Middle Task",
			duration_minutes=20,
			priority="medium",
			category="feeding",
			time_of_day="09:00",
		)
	)

	scheduler = Scheduler(pet=pet)
	ordered = scheduler.sort_by_time()

	assert [task.time_of_day for task in ordered] == ["07:15", "09:00", "11:30"]


def test_recurrence_logic_daily_complete_creates_following_day_task() -> None:
	owner = Owner(name="Alex", available_minutes=60)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	task = Task(
		title="Daily Walk",
		duration_minutes=20,
		priority="medium",
		category="exercise",
		frequency="daily",
	)
	pet.add_task(task)

	task.mark_complete()

	tasks = pet.get_tasks()
	assert len(tasks) == 2
	new_task = [pet_task for pet_task in tasks if pet_task is not task][0]
	assert new_task.due_date == date.today() + timedelta(days=1)
	assert new_task.completed is False


def test_conflict_detection_flags_duplicate_times() -> None:
	owner = Owner(name="Alex", available_minutes=120)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)

	pet.add_task(
		Task(
			title="Walk",
			duration_minutes=20,
			priority="high",
			category="exercise",
			time_of_day="08:00",
		)
	)
	pet.add_task(
		Task(
			title="Feed",
			duration_minutes=10,
			priority="high",
			category="feeding",
			time_of_day="08:00",
		)
	)

	scheduler = Scheduler(pet=pet)
	conflicts = scheduler.detect_time_conflicts()

	assert len(conflicts) == 1
	assert "time conflict at 08:00" in conflicts[0]
	assert "Buddy: Walk" in conflicts[0]
	assert "Buddy: Feed" in conflicts[0]


# ----------------------------------------------------------------------
# Reliability extension tests
# ----------------------------------------------------------------------


def _build_owner_with_two_pets(available_minutes: int = 120) -> tuple[Owner, Pet, Pet]:
	owner = Owner(name="Alex", available_minutes=available_minutes)
	pet1 = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	pet2 = Pet(name="Mochi", species="Cat", age=2, owner=owner)
	return owner, pet1, pet2


def test_reliability_score_penalizes_conflicts() -> None:
	owner, pet1, pet2 = _build_owner_with_two_pets()
	pet1.add_task(
		Task(title="Walk", duration_minutes=20, priority="high", category="exercise", time_of_day="08:00")
	)
	pet2.add_task(
		Task(title="Feed", duration_minutes=10, priority="high", category="feeding", time_of_day="08:00")
	)

	scheduler = Scheduler(pet=pet1)
	plan = scheduler.build_plan()
	conflicts = scheduler.detect_time_conflicts()
	tasks = scheduler.filter_tasks(completed=False)

	scorer = ReliabilityScorer()
	report = scorer.evaluate(plan, conflicts, tasks)

	assert report.score < 1.0
	assert any("time conflict" in signal for signal in report.signals)


def test_reliability_score_penalizes_skipped_high_priority() -> None:
	owner = Owner(name="Alex", available_minutes=10)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	pet.add_task(
		Task(title="Big Walk", duration_minutes=10, priority="high", category="exercise", time_of_day="08:00")
	)
	pet.add_task(
		Task(title="Vet Trip", duration_minutes=10, priority="high", category="health", time_of_day="09:00")
	)

	scheduler = Scheduler(pet=pet)
	plan = scheduler.build_plan()
	tasks = scheduler.filter_tasks(completed=False)

	scorer = ReliabilityScorer()
	report = scorer.evaluate(plan, conflicts=[], tasks=tasks)

	# One high-priority task got skipped because the budget only fits one.
	assert any("high-priority" in signal for signal in report.signals)
	assert report.score < 1.0


def test_reliability_status_mapping() -> None:
	scorer = ReliabilityScorer()
	assert scorer.status_from_score(0.95) == "high"
	assert scorer.status_from_score(0.80) == "high"
	assert scorer.status_from_score(0.79) == "medium"
	assert scorer.status_from_score(0.60) == "medium"
	assert scorer.status_from_score(0.59) == "low"
	assert scorer.status_from_score(0.0) == "low"


def test_guardrails_drop_low_priority_when_score_is_low(tmp_path, monkeypatch) -> None:
	monkeypatch.setattr(pawpal_system, "RELIABILITY_LOG_PATH", tmp_path / "runs.jsonl")

	# Tight budget + conflict + a low-priority task that can be dropped.
	owner = Owner(name="Alex", available_minutes=35, reliability_min_score=0.9)
	pet1 = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	pet2 = Pet(name="Mochi", species="Cat", age=2, owner=owner)

	pet1.add_task(
		Task(title="Walk", duration_minutes=20, priority="high", category="exercise", time_of_day="08:00")
	)
	pet2.add_task(
		Task(title="Feed", duration_minutes=10, priority="high", category="feeding", time_of_day="08:00")
	)
	pet1.add_task(
		Task(title="Brush", duration_minutes=5, priority="low", category="grooming", time_of_day="10:00")
	)

	scheduler = Scheduler(pet=pet1)
	result = scheduler.build_reliable_plan()

	scheduled_titles = [task["title"] for task in result["plan"]["scheduled_tasks"]]
	skipped_titles = [item["task"]["title"] for item in result["plan"]["skipped_tasks"]]

	# The low-priority "Brush" task should be dropped by the guardrail.
	assert "Brush" not in scheduled_titles
	assert "Brush" in skipped_titles
	assert any("Dropped low-priority" in action for action in result["reliability"]["actions"])


def test_reliable_plan_reorders_when_conflicts_exist(tmp_path, monkeypatch) -> None:
	monkeypatch.setattr(pawpal_system, "RELIABILITY_LOG_PATH", tmp_path / "runs.jsonl")

	owner = Owner(name="Alex", available_minutes=120, reliability_min_score=0.9)
	pet1 = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	pet2 = Pet(name="Mochi", species="Cat", age=2, owner=owner)
	pet1.add_task(
		Task(title="Late", duration_minutes=10, priority="high", category="general", time_of_day="20:00")
	)
	pet1.add_task(
		Task(title="Morning Walk", duration_minutes=20, priority="high", category="exercise", time_of_day="08:00")
	)
	pet2.add_task(
		Task(title="Feed", duration_minutes=10, priority="high", category="feeding", time_of_day="08:00")
	)

	scheduler = Scheduler(pet=pet1)
	result = scheduler.build_reliable_plan()

	assert any(
		"Reordered scheduled tasks by time-of-day" in action
		for action in result["reliability"]["actions"]
	)
	scheduled_times = [task["time_of_day"] for task in result["plan"]["scheduled_tasks"]]
	assert scheduled_times == sorted(scheduled_times)


def test_reliability_log_written(tmp_path, monkeypatch) -> None:
	log_path = tmp_path / "runs.jsonl"
	monkeypatch.setattr(pawpal_system, "RELIABILITY_LOG_PATH", log_path)

	owner = Owner(name="Alex", available_minutes=60)
	pet = Pet(name="Buddy", species="Dog", age=3, owner=owner)
	pet.add_task(
		Task(title="Walk", duration_minutes=20, priority="high", category="exercise", time_of_day="08:00")
	)

	scheduler = Scheduler(pet=pet)
	scheduler.build_reliable_plan()

	assert log_path.exists()
	lines = log_path.read_text(encoding="utf-8").strip().splitlines()
	assert len(lines) == 1
	entry = json.loads(lines[0])
	assert entry["owner"] == "Alex"
	assert entry["pet"] == "Buddy"
	assert "reliability" in entry
	assert "score" in entry["reliability"]


def test_reliability_report_to_dict_round_trips() -> None:
	report = ReliabilityReport(
		score=0.75,
		status="medium",
		signals=["a", "b"],
		actions=["did x"],
	)
	payload = report.to_dict()
	assert payload["score"] == 0.75
	assert payload["status"] == "medium"
	assert payload["signals"] == ["a", "b"]
	assert payload["actions"] == ["did x"]
	assert "generated_at" in payload
