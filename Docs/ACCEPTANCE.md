# University Acceptance Checklist

Use only non-production student data. Record the server CPU, memory, operating
system, Docker versions, deployed commit, engine version, seed, and configuration
with every result.

## Functional acceptance

1. Sign in with the bootstrap administrator and verify password rotation is
   mandatory.
2. Upload one invalid CSV, one valid CSV, and one valid XLSX. Confirm validation
   blocks invalid data and the audit trail records upload and validation.
3. Complete uniform- and mixed-inventory runs. Confirm only the deterministic
   sufficient room subset is active and unused inventory is reported.
4. While a run is active, refresh and reconnect to progress, cancel a test run,
   and queue two additional runs. Exactly one run may be `running`; the other
   must remain visibly `queued`.
5. Search rooms and students, inspect a pair, and download every Excel, PDF, CSV,
   and JSON artifact. Confirm every download is audited.
6. Delete a test run and confirm its upload, normalized records, assignments,
   rooms, and artifacts are unavailable while the non-identifying tombstone
   remains.

## Performance and determinism

Run each baseline three times on the deployment server with CP-SAT disabled:

```bash
python -m benchmarks.run_benchmark --students 1000 --time-limit 300 --output benchmarks/latest-1000.json
python -m benchmarks.run_benchmark --students 5000 --time-limit 300 --output benchmarks/latest-5000.json
```

Run the same data, seed, configuration, and engine version through the worker.
Compare median `runtime_seconds`; worker optimizer runtime must be no more than
5% above the CLI median. During optimization, repeatedly load run history,
room/student result pages from a completed run, and `/api/health/ready`; requests
must remain responsive.

Repeat the same run twice and compare `assignments.csv` SHA-256 values. They must
match. Also compare `data_hash`, `config_hash`, engine version, and seed in
`run_metadata.json`.

## Report verification

- Open the workbook in the university-supported Excel version. Verify all five
  Persian RTL sheets, frozen headers, filters, names, room IDs, capacities,
  validation findings, and summary metrics.
- Render the PDF on screen and paper. Verify Persian shaping, RTL reading order,
  page breaks, room rosters, and page numbering.
- Verify CSV headers remain stable English identifiers and files decode as
  UTF-8 with BOM.
- Recompute SHA-256 for every artifact and compare it with the stored manifest.

## Operations and security

Run backend/frontend tests, `pip-audit`, `npm audit`, migration upgrade/downgrade,
and container builds. Take an encrypted backup, restore it into non-production,
then verify login, history, assignments, and one artifact hash. Confirm TLS,
host disk encryption, private-volume permissions, 30-day backup rotation, health
checks, and incident contacts before sign-off.
