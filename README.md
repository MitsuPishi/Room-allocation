# UniMate Room Assignment

UniMate is a validated, reproducible room-assignment system for university
dormitories. It uses the original housing questionnaire and a transparent
multi-criteria optimizer. The deprecated clustering workflow is retained only
under `legacy/`.

## What the system claims

- Every accepted row is validated against an explicit questionnaire schema.
- Room capacities are respected and occupancy differs by at most one student.
- Compatibility scores are reproducible and explainable by four dimensions.
- The optimizer protects the weakest student and lower-quality rooms before
  improving the global mean.
- Large runs are reported as `best_found`; global optimality is not claimed.

The system does **not** yet claim that its scores predict roommate satisfaction.
No historical outcome labels are available. See
[`Docs/METHODOLOGY.md`](Docs/METHODOLOGY.md) for the research and validation
policy.

## Supported input

Use the original Persian or equivalent English questionnaire fields:

- sleep window
- wake window
- noise tolerance
- study environment
- cleanliness
- optional faculty, major, age, residence, ethnicity, and religion
- optional student ID and name

One-hot encoded files are intentionally rejected. Religion, ethnicity, and
residence are retained only for authorized auditing and are never used in
compatibility scores.

## Installation

Python 3.12 is the supported runtime.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Do not reuse the old checked-in Linux virtual environment on Windows.

## Streamlit

```powershell
streamlit run app.py
```

The default example is `Data/MOCK_DATA-Women.csv`. Capacity defaults to six and
the production scoring weights are fixed equally across the four dimensions.
Adjustable weights are clearly marked as sensitivity analysis.

## Command line

```powershell
python -m engine assign `
  --input Data/MOCK_DATA-Women.csv `
  --output-dir results/women-2026 `
  --capacity 6 `
  --time-limit 300 `
  --seed 42
```

Each run produces:

- `assignments.csv`
- `room_metrics.csv`
- `student_metrics.csv`
- `validation_report.csv`
- `run_metadata.json`

Metadata includes the algorithm and scoring versions, seed, configuration,
runtime, data hash, configuration hash, metrics, and search history.

## Tests and benchmarks

```powershell
python -m unittest discover -s tests -v
python benchmarks/run_benchmark.py --students 1000 --time-limit 300
python benchmarks/run_benchmark.py --students 5000 --time-limit 300
```

The exact total-score oracle is limited to small instances and is used only to
measure heuristic gaps. It does not replace the production fairness objective.

## Public engine API

```python
from engine import (
    CompatibilityScorer,
    OptimizationConfig,
    RoomOptimizer,
    parse_student_survey,
)

parsed = parse_student_survey(raw_dataframe, strict=True)
scores = CompatibilityScorer().score(parsed.data)
result = RoomOptimizer(
    OptimizationConfig(capacity=6, time_limit_seconds=300, seed=42)
).optimize(parsed.data, scores)
```

## License

MIT. See [`LICENSE`](LICENSE).
