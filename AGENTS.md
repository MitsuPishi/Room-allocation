# Agent Notes

## Runtime

- Prefer Python 3.12 for this project.
- Use `py -3.12` or `.\.venv\Scripts\python.exe`; avoid relying on bare `python` because Windows may route it to the Microsoft Store alias.
- Python 3.14 may be installed on this PC, but it is not the primary runtime for this repo.
- OR-Tools CP-SAT can terminate the Python process on this Windows setup, including near the end of Streamlit optimization runs. Keep CP-SAT off for normal local testing, but leave the explicit opt-in available for experiments.
- Use Python 3.12 for Streamlit and regular optimizer tests. Exact-oracle tests and CP-SAT benchmark validation need a separate solver-safe environment.

## Environment Setup

Create or replace the project virtual environment with Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run commands through the venv:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\streamlit.exe run app.py
```

## Project Context

- The app is a Streamlit dashboard for validated university dorm room assignment.
- Core engine code lives in `engine/`.
- Tests live in `tests/`.
- The optimizer supports both uniform capacity and mixed room inventories.
- Mixed capacity syntax is count-by-capacity, for example `100x6,20x4`.
- `room_size` means assigned occupancy.
- `room_capacity` means physical bed capacity.
- Surplus beds are treated as vacancies; over-supply is expected to be rare.

## Recent Implementation Notes

- `OptimizationConfig.capacity_mix` accepts compact strings or tuples such as `((100, 6), (20, 4))`.
- CLI supports `--capacity-mix "100x6,20x4"`; this overrides `--capacity`.
- Streamlit has a variable room capacity option in the sidebar.
- Streamlit also exposes CP-SAT neighborhood refinement in Advanced optimizer. It defaults off on this Windows setup and warns before enabling.
- CLI supports `--allow-unsafe-cp-sat` to force CP-SAT despite the runtime safety guard.
- Metadata includes room inventory, generated capacities, total beds, occupied beds, and vacancies.
- The legacy `DormOptimizationEngine` accepts mixed `df_rooms["capacity"]` values.

## Worktree Notes

- `app.py` may show both staged and unstaged changes because it had existing staged edits before the variable-capacity work.
- `requirements-minimal.txt` was already untracked and should not be removed unless the user asks.
