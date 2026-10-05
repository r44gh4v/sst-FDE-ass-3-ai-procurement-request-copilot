# Comparison results (10 cases, same set for both)

| Metric | A: Single agent | B: Staged 2-agent |
|---|---:|---:|
| Minimum checks passed | 9/10 | 9/10 |
| Correct next action | 9/10 | 9/10 |
| Guardrail overrides | 0 | 0 |
| Ungrounded $ numbers in summary | 0 | 1 |
| Avg latency | 15.8 s | 22.7 s |
| Avg LLM calls | 5.1 | 5.2 |
| Avg tool calls | 5.1 | 4.2 |
