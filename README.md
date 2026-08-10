# UniMate University Room Allocation

UniMate is an on-premises, auditable dorm-room assignment product. A Persian
React dashboard is backed by FastAPI, PostgreSQL, Redis/RQ, and the validated
Python optimization engine. Optimization runs in a dedicated worker process so
uploads, reporting, and dashboard traffic do not compete with the solver.

## Product capabilities

- Persian RTL workflow for questionnaire upload, validation, configuration,
  progress monitoring, investigation, and export.
- Reproducible fairness-first assignment for uniform or mixed room inventories.
- Automatic selection of the smallest sufficient room subset before roommate
  compatibility optimization.
- One local administrator with forced initial password rotation, revocable
  sessions, CSRF protection, login throttling, and authenticated downloads.
- Durable run history and non-PII audit events until explicit administrator
  deletion.
- Persian Excel and PDF reports plus UTF-8 CSV and JSON reproducibility files.
- Encrypted nightly backups with a rolling 30-day default.

The optimizer reports large runs as `best_found`; it does not claim global
optimality or validated prediction of roommate satisfaction. See
[`Docs/METHODOLOGY.md`](Docs/METHODOLOGY.md).

## Production deployment

Requirements: a university-managed Linux server, Docker Engine with Compose,
and an HTTPS reverse proxy.

```bash
cp .env.example .env
# Replace every placeholder in .env with independent, strong secrets.
docker compose up -d --build
docker compose ps
```

The dashboard listens on port `8080` by default. TLS must terminate at the
university reverse proxy, which forwards the original `Host`,
`X-Forwarded-For`, and `X-Forwarded-Proto` headers. The initial administrator
must change the deployment password on first login.

Do not enable `UNIMATE_CP_SAT_DEFAULT` until the 1,000- and 5,000-student
acceptance benchmarks pass on the deployment server.

Detailed deployment, backup, restore, upgrade, and incident procedures are in
[`Docs/OPERATIONS.md`](Docs/OPERATIONS.md). Security controls and data deletion
behavior are in [`Docs/SECURITY.md`](Docs/SECURITY.md). The final server-side
sign-off procedure is in [`Docs/ACCEPTANCE.md`](Docs/ACCEPTANCE.md).

## Local development

Python 3.12 is the supported backend runtime.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:UNIMATE_INLINE_JOBS="true"
.\.venv\Scripts\uvicorn.exe server.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

The development administrator defaults to `admin` / `change-me-now` and must be
changed immediately. Never use those values in production.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall -q engine server tests migrations benchmarks
cd frontend
npm.cmd run build
npm.cmd run e2e
npm.cmd audit --audit-level=moderate
```

For deployment benchmarks:

```powershell
.\.venv\Scripts\python.exe benchmarks\run_benchmark.py --students 1000 --time-limit 300
.\.venv\Scripts\python.exe benchmarks\run_benchmark.py --students 5000 --time-limit 300
```

## CLI and Python API

The web migration does not remove the reproducible CLI or engine API.

```powershell
.\.venv\Scripts\python.exe -m engine assign `
  --input Data/MOCK_DATA-Women.csv `
  --output-dir results/women-2026 `
  --capacity-mix "100x6,20x4" `
  --time-limit 300 `
  --seed 42
```

```python
from engine import CompatibilityScorer, OptimizationConfig, RoomOptimizer

scores = CompatibilityScorer().score(normalized_students)
result = RoomOptimizer(
    OptimizationConfig(capacity_mix=((100, 6), (20, 4)), seed=42)
).optimize(normalized_students, scores)
```

## Repository layout

- `frontend/`: Persian React/TypeScript dashboard.
- `server/`: FastAPI, security, persistence, worker, and export services.
- `engine/`: validated scoring and optimization engine.
- `migrations/`: PostgreSQL/SQLAlchemy schema migrations.
- `ops/`: reverse-proxy and encrypted backup tooling.
- `tests/`: engine and API integration tests.

## License

MIT. See [`LICENSE`](LICENSE).
