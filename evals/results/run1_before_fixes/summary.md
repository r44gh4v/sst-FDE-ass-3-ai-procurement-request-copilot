# Comparison results (10 cases, same set for both)

| Metric | A: Single agent | B: Staged 2-agent |
|---|---:|---:|
| Minimum checks passed | 10/10 | 9/10 |
| Correct next action | 7/10 | 6/10 |
| Guardrail overrides | 1 | 0 |
| Ungrounded $ numbers in summary | 1 | 2 |
| Avg latency | 16.3 s | 21.8 s |
| Avg LLM calls | 5.1 | 5.1 |
| Avg tool calls | 5.1 | 4.1 |
