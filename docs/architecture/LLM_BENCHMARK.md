# Local Model Benchmark

| | |
|---|---|
| Date | 2026-11-14 |
| Status | **Diagnostic sample only; not qualified for release lock.** |
| Recommended local candidate | `qwen2.5:3b` (provisional; only model installed during this run) |
| Related | [System architecture](./system-architecture.md), [Database schema](./database-schema.md) |

## Host and Configuration

| Component | Observed configuration |
|---|---|
| OS | Windows 11 Home Single Language, build 26200 |
| CPU | AMD Ryzen 5 7430U, 6 cores / 12 logical processors |
| Memory | 15.3 GiB visible to Windows |
| Ollama model | `qwen2.5:3b`, Q4_K_M, 3.1B parameters, 1.93 GB installed |
| Model execution | CPU-only; Ollama reported 0 bytes of VRAM use |
| Ollama context | 2048 tokens |
| Roleplay output limit | 160 tokens |
| Coach output limit | 1200 tokens |
| LLM timeout | 180 seconds |
| Speech model | `tiny.en`, CPU, int8 |

The local `.env` used these values. The same candidate and budgets are
recommended in `.env.example`; model names remain configuration, not
application/frontend constants.

## Run and Results

One real run of `backend/tools/benchmark_llm.py` exercised nine roleplay cases
(three scenarios × strong/average/weak answers) and three Coach fixtures. The
roleplay warm p95 excludes the first, cold sample. This sample count is useful
for diagnosis only; it is not the script's 20-run model-lock qualification.

| Area | Measure | Result | Interpretation |
|---|---|---:|---|
| Roleplay | Cold first reply | 12,782 ms | Includes cold model load |
| Roleplay | Warm reply p95 | 6,923 ms | Passes the 8,000 ms diagnostic threshold |
| Roleplay | Successful / format-clean | 9/9; 100% | No Markdown or stage directions |
| Roleplay | Exactly one question | 77.8% | Seven of nine samples |
| Coach | Valid on first try | 100% (3/3) | No repair retry in these fixtures |
| Coach | Valid evidence IDs | 100% (3/3) | All cited IDs were candidate turns |
| Coach | Strong minus weak score | 52 points | Strong 89; weak 37 |
| Coach | Average fixture score | 20 | Lower than the weak fixture; ordering needs more samples/review |
| Coach | Evaluation p95 | 79,591 ms | Fails the 60,000 ms target |
| Whisper | `tiny.en` load + warmup | 2,586 ms; ready | No labeled audio fixture exists, so transcription latency and WER are unavailable |
| Resources | Lowest available host RAM | 1,471 MiB | Sampled during this single run |

A separate real HTTP E2E session completed with `qwen2.5:3b`: create session,
start interview, submit a typed answer, end session, and complete Coach
evaluation. The evaluation scored 82 and took 76.6 seconds. Live health reported
SQLite, Ollama, and faster-whisper ready after warmup.

## Qualification and Recommendation

The model is a **provisional local default**, not a release-qualified lock. This
run did not meet the benchmark harness's release criteria:

- It ran once, rather than the required 20 repeated runs; score variability
  cannot be measured and human behavior review was not performed.
- Coach evaluation p95 was 79.6 seconds, above the 60-second target.
- There is no labeled audio fixture to measure WER.
- The average fixture scored below the weak fixture in this small sample.

Do not treat these results as statistically conclusive, and do not tag the MVP
release until the failed/unmeasured criteria are addressed and a qualifying
benchmark plus human behavior review has been recorded.
