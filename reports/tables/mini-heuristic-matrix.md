Benchmark: benchmarks/mini (43 theorems), policy=heuristic, k=10, budget: 50 expansions / 400 Lean calls / depth 12 / 60s per theorem

| Method | Solved | Solved % | Lean calls (total) | Lean calls / solved | Expansions / solved | Avg proof length | Time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Greedy | 37/43 | 86.05 | 564 | 8.784 | 1.405 | 1.405 | 6.37 |
| BFS | 38/43 | 88.37 | 1417 | 12.605 | 1.789 | 1.447 | 15.42 |
| Beam-4 | 37/43 | 86.05 | 1046 | 10.676 | 1.595 | 1.405 | 13.65 |
| Beam-8 | 38/43 | 88.37 | 1273 | 12.605 | 1.789 | 1.447 | 12.58 |
| Beam-16 | 38/43 | 88.37 | 1417 | 12.605 | 1.789 | 1.447 | 12.1 |
| Best-first | 38/43 | 88.37 | 1417 | 12.605 | 1.789 | 1.447 | 13.49 |
