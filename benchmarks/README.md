# Benchmarks

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe benchmarks\run_benchmark.py --students 1000 --time-limit 300
.\.venv\Scripts\python.exe benchmarks\run_benchmark.py --students 5000 --time-limit 300
```

The 5,000-row workload repeats the 1,000-row mock survey to test computational
scaling. Its quality metrics are not evidence of real-world effectiveness.

The benchmark records:

- random, greedy, and optimized metrics;
- total within-room pair scores;
- score-matrix memory;
- sampled peak process RSS;
- runtime and machine information; and
- pass/fail acceptance checks.

## Observed development-machine smoke results

August 10, 2026, Windows 11, Python 3.12, capacity six:

| Students | Search budget | Matrix | Peak RSS | Worst utility | P10 room | Mean utility |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 2 s | 1.9 MB | 101.8 MB | 54.4 | 63.6 | 87.3 |
| 5,000 | 2 s | 47.7 MB | 337.1 MB | 25.2 | 69.4 | 96.0 |

Both smoke runs completed below five minutes and one GiB, and the optimized
assignments were not worse than the greedy baseline under the lexicographic
fairness objective. Re-run the full five-minute protocol on deployment hardware
before publishing performance claims.
