# UniMate Methodology and Validation Protocol

## 1. Decision problem

The production problem is a fixed-capacity coalition-formation problem:
partition every eligible student into balanced rooms while maximizing roommate
compatibility. For rooms larger than two, exact global optimization becomes
computationally hard at realistic university scale. UniMate therefore uses an
auditable hybrid search and reports large solutions as `best_found`.

Relevant background:

- Cseh, Fleiner, and Harjan, *Pareto optimal coalitions of fixed size*:
  https://arxiv.org/abs/1901.06737
- Brandt, Busing, and Engelhardt, *Patient-to-room Assignment under
  Consideration of Roommate Compatibility*:
  https://arxiv.org/abs/2503.01021
- Google OR-Tools CP-SAT status definitions:
  https://developers.google.com/optimization/cp/cp_solver

## 2. Input validity

The raw questionnaire is the canonical source. Positional column renaming and
pre-encoded feature matrices are prohibited because they can silently change
field meaning.

The parser:

1. matches explicit Persian and English aliases;
2. recovers known spreadsheet-corrupted time labels;
3. rejects unknown required categories;
4. reports optional missing values without imputing behavioral answers;
5. generates deterministic IDs only when the legacy mock files lack IDs; and
6. emits a row-level validation report.

The known time categories are ordinal:

- sleep: `10-11`, `11-12`, `12-1`, `1-2`, `2-3`;
- wake: `4-5`, `5-6`, `6-7`, `7-8`.

Strings such as `11-Oct` and `5-Apr` are spreadsheet representations of the
first category in each corresponding sequence.

## 3. Compatibility score

Version `compatibility-v1` returns a symmetric integer score from 0 to 100.
Production weights are fixed:

| Dimension | Weight | Rule |
| --- | ---: | --- |
| Cleanliness | 25 | Full credit for equal category |
| Noise tolerance | 25 | Full credit for equal category |
| Study environment | 25 | Full credit for equal category |
| Sleep/wake schedule | 25 | Linear ordinal similarity, split equally |

Schedule contribution is:

```text
25 * ((1 - abs(sleep_i - sleep_j) / 4)
    + (1 - abs(wake_i - wake_j) / 3)) / 2
```

The score excludes age, faculty, major, religion, ethnicity, and residence.
Religion, ethnicity, and residence must not influence assignments unless a
future approved housing policy introduces a separately documented hard rule.

Adjustable UI weights are sensitivity analysis, not a production policy.

## 4. Fairness objective

For each student, utility is the mean pair score with all roommates. Room quality
is the lowest student utility in that room.

Solutions are compared lexicographically:

1. maximize the minimum student utility;
2. maximize the 10th-percentile room quality;
3. maximize mean student utility; and
4. minimize variance in room quality.

This prevents a high average from concealing a small number of very poor rooms.

## 5. Search algorithm

1. Compute target room sizes so occupancy differs by at most one.
2. Rank students by how easily they can be placed with highly compatible peers.
3. Place the hardest students first and fill rooms using prospective minimum and
   mean pair compatibility.
4. Repeatedly target low-quality rooms and evaluate cross-room swaps.
5. Run CP-SAT on a small set of weak rooms, preserving the current minimum
   utility floor while maximizing local total compatibility.
6. Repeat from deterministic seeded starts and retain the lexicographically best
   solution.

The full 5,000-student pair matrix uses signed 16-bit integers, approximately
50 MB. CP-SAT is not applied to the global large-scale pair-room formulation.

## 6. Reproducibility

Every result records:

- normalized data hash;
- complete configuration hash;
- algorithm and scoring versions;
- random seed;
- runtime and solver/search events; and
- room-level and student-level metrics.

Given the same environment, data, configuration, and seed, the assignment is
deterministic.

## 7. Required empirical validation

Until real outcome data exists, UniMate is a transparent decision-support
optimizer, not a validated predictive model.

Before claiming real-world effectiveness:

1. preregister outcomes such as satisfaction, conflict reports, and room-change
   requests;
2. obtain appropriate consent and privacy review;
3. compare optimized assignment against an operational baseline;
4. report confidence intervals and subgroup audits;
5. calibrate weights only on training periods and evaluate on held-out cohorts;
6. publish negative and null findings; and
7. retain a human appeal and override process.

## 8. Benchmark protocol

Report random and optimized baselines for 1,000 and 5,000 students at capacity
six. Record hardware, Python version, seed, runtime, matrix memory, fairness
metrics, and total pair score. On small instances, compare total pair score with
the exact oracle and report both solver status and optimality gap.
