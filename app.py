import streamlit as st
from pawpal_system import Owner, Pet, Scheduler, Task

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")


def initialize_session_objects() -> None:
    """Create persistent domain objects once per Streamlit session."""
    if "owner" not in st.session_state:
        st.session_state.owner = Owner(name="Jordan", available_minutes=120)

    if "pet" not in st.session_state:
        st.session_state.pet = Pet(
            name="Mochi",
            species="dog",
            age=2,
            owner=st.session_state.owner,
        )


def task_table_rows() -> list[dict[str, object]]:
    """Return task rows for table display."""
    return [task.to_dict() for task in st.session_state.pet.get_tasks()]


def task_objects_to_rows(tasks: list[Task]) -> list[dict[str, object]]:
    """Convert task objects into rows for Streamlit tables."""
    return [task.to_dict() for task in tasks]


def conflict_rows(conflicts: list[str]) -> list[dict[str, str]]:
    """Convert scheduler conflict messages into structured rows for display."""
    rows: list[dict[str, str]] = []

    for warning in conflicts:
        details = warning.removeprefix("Warning: ").strip().rstrip(".")
        time_slot = "unspecified"
        tasks = details

        if details.startswith("time conflict at ") and " for " in details:
            after_prefix = details.removeprefix("time conflict at ")
            time_slot, tasks = after_prefix.split(" for ", maxsplit=1)

        rows.append(
            {
                "time": time_slot,
                "tasks_in_conflict": tasks,
                "impact": "Owner may not complete all tasks at this time",
            }
        )

    return rows


initialize_session_objects()

st.markdown(
    """
Welcome to the PawPal+ starter app.

This file is intentionally thin. It gives you a working Streamlit app so you can start quickly,
but **it does not implement the project logic**. Your job is to design the system and build it.

Use this app as your interactive demo once your backend classes/functions exist.
"""
)

with st.expander("Scenario", expanded=True):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps a pet owner plan care tasks
for their pet(s) based on constraints like time, priority, and preferences.

You will design and implement the scheduling logic and connect it to this Streamlit UI.
"""
    )

with st.expander("What you need to build", expanded=True):
    st.markdown(
        """
At minimum, your system should:
- Represent pet care tasks (what needs to happen, how long it takes, priority)
- Represent the pet and the owner (basic info and preferences)
- Build a plan/schedule for a day that chooses and orders tasks based on constraints
- Explain the plan (why each task was chosen and when it happens)
"""
    )

st.divider()

st.subheader("Adding a Pet")
owner_name = st.text_input("Owner name", value=st.session_state.owner.name)
pet_name = st.text_input("Pet name", value=st.session_state.pet.name)
species = st.selectbox("Species", ["dog", "cat", "other"])
age = st.number_input("Pet age", min_value=0, max_value=50, value=int(st.session_state.pet.age))

st.session_state.owner.name = owner_name

if st.button("Add or update pet"):
    st.session_state.pet = Pet(
        name=pet_name,
        species=species,
        age=int(age),
        owner=st.session_state.owner,
    )
    st.success(f"Saved pet profile for {st.session_state.pet.name}.")

st.markdown("### Tasks")
st.caption("Add a few tasks. In your final version, these should feed into your scheduler.")

col1, col2, col3 = st.columns(3)
with col1:
    task_title = st.text_input("Task title", value="Morning walk")
with col2:
    duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
with col3:
    priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)

if st.button("Add task"):
    st.session_state.pet.add_task(
        Task(
            title=task_title,
            duration_minutes=int(duration),
            priority=priority,
            category="general",
        )
    )

rows = task_table_rows()

if rows:
    st.write("Current tasks:")
    st.table(rows)
else:
    st.info("No tasks yet. Add one above.")

st.divider()

st.subheader("Build Schedule")
st.caption("Generate a schedule from your current tasks and available time.")

strict_mode = st.toggle(
    "Strict reliability mode",
    value=False,
    help=(
        "When on, raises the minimum reliability score to 0.8 so the planner "
        "more aggressively reorders or drops low-priority tasks."
    ),
)

if st.button("Generate schedule"):
    if strict_mode:
        st.session_state.owner.reliability_min_score = 0.8
    else:
        st.session_state.owner.reliability_min_score = 0.6

    scheduler = Scheduler(pet=st.session_state.pet)
    incomplete_tasks = scheduler.filter_tasks(completed=False)
    sorted_by_priority = scheduler.sort_by_priority()
    sorted_by_time = scheduler.sort_by_time()
    reliable_result = scheduler.build_reliable_plan()
    plan = reliable_result["plan"]
    conflicts = reliable_result["conflicts"]
    reliability = reliable_result["reliability"]

    st.success("Schedule generated.")
    st.write(f"Time budget: {plan['time_budget']} minutes")
    st.write(f"Total time used: {plan['total_time_used']} minutes")
    st.write(f"Remaining minutes: {plan['remaining_minutes']}")

    st.markdown("### Reliability report")
    status = reliability["status"]
    score = reliability["score"]
    if status == "high":
        st.success(f"Reliability: HIGH (score {score:.2f})")
    elif status == "medium":
        st.info(f"Reliability: MEDIUM (score {score:.2f})")
    else:
        st.warning(
            f"Reliability: LOW (score {score:.2f}) — review the signals and "
            "actions below before trusting this plan."
        )

    if reliability["signals"]:
        st.markdown("**Signals affecting confidence:**")
        for signal in reliability["signals"]:
            st.write(f"- {signal}")

    if reliability["actions"]:
        st.markdown("**Guardrail actions taken:**")
        for action in reliability["actions"]:
            st.write(f"- {action}")
    else:
        st.caption("No guardrail adjustments were needed.")

    st.markdown("### Scheduler insights")
    if incomplete_tasks:
        st.success(f"Found {len(incomplete_tasks)} incomplete task(s) ready for scheduling.")
    else:
        st.warning("No incomplete tasks found. Add tasks before generating a schedule.")

    if conflicts:
        st.warning(
            f"{len(conflicts)} scheduling conflict(s) detected. Review the overlaps below before relying on this plan."
        )
        st.table(conflict_rows(conflicts))
        with st.expander("How to resolve these conflicts", expanded=False):
            st.markdown(
                """
- Move one overlapping task to a different time slot.
- Shorten or split long tasks if possible.
- Keep high-priority care tasks at fixed times first.
"""
            )
    else:
        st.success("No task time conflicts were detected.")

    st.markdown("### Tasks sorted by priority")
    if sorted_by_priority:
        st.table(task_objects_to_rows(sorted_by_priority))
    else:
        st.warning("No tasks fit the available time budget for priority sorting.")

    st.markdown("### Tasks sorted by time")
    if sorted_by_time:
        st.table(task_objects_to_rows(sorted_by_time))
    else:
        st.warning("No tasks with schedulable times are available for time-based sorting.")

    st.markdown("### Scheduled tasks")
    if plan["scheduled_tasks"]:
        st.table(plan["scheduled_tasks"])
    else:
        st.info("No tasks were scheduled.")

    if plan["skipped_tasks"]:
        st.markdown("### Skipped tasks")
        skipped_rows = [
            {
                "title": item["task"]["title"],
                "duration_minutes": item["task"]["duration_minutes"],
                "priority": item["task"]["priority"],
                "reason": item["reason"],
            }
            for item in plan["skipped_tasks"]
        ]
        st.table(skipped_rows)

    st.markdown("### Why this plan")
    for reason in reliable_result["reasoning"]:
        st.write(f"- {reason}")
