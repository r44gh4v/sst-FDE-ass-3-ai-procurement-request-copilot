# Architecture Decision Memo

## Decision

Ship **Architecture A: the single agent** (one agent with 4 tools + deterministic guardrail).

## Evidence

Same 10 cases for both: the 6 public cases plus 4 extra cases for the other requests. Results are in
`evals/results/`; the run before my fixes is in `evals/results/run1_before_fixes/`.

| Metric | Single agent | Staged / 2-agent |
|---|---:|---:|
| Official public runner | 6/6 | 6/6 |
| Minimum checks (10 cases) | 9/10 | 9/10 |
| Correct next action | 9/10 | 9/10 |
| Guardrail overrides | 0 | 0 |
| Ungrounded $ numbers | 0 | 1 |
| Avg latency | **15.8 s** | 22.7 s |
| Avg LLM calls | 5.1 | 5.2 |
| Avg tool calls | 5.1 | 4.2 |
| Correct action before fixes | 7/10 | 6/10 |

Policy failures found manually: none. Approvals and factual flags come from code, so they are identical in both.
Both miss the same case: TaskFlow Pro, where a company-wide TaskFlow licence already exists. Both agents decided
"Pro" might be a separate product and recommended buying it instead of reuse. Staged also wrote "$4,000 over
budget" in one summary: correct maths, but computed by the model instead of coming from a tool.

## Trade-offs

- Staged gives a cleaner split (research vs. decide), but the reviewer only sees the researcher's notes, so a
  detail left out of the notes cannot be recovered. The single agent reads the raw tool results itself.
- Staged made no difference to accuracy, was about 7 s slower, and adds a second prompt and a handoff format.
- The biggest gain came from **tightening the deterministic rules**: "clarify" only when information is
  missing, "escalate" only when evidence is unavailable or conflicting. That took both architectures from
  6-7/10 to 9/10. Strict logic in code mattered more than the number of agents.

## Risks / limitations

- 10 cases, one run each, one model (`nemotron-3-super-120b`). Results vary between runs: an earlier run had the single agent at 10/10. A 1-case gap is noise, so I would rerun several times on more cases before production.
- "Does an existing licence cover this?" is the weakest point. A human should confirm every overlap judgement.
- Injection detection is a regex plus the LLM. Injected text still cannot change approvals, because code computes them.
- About 15 s latency is fine for back-office requests, not for live chat.

## Why this is the right MVP

The strict procurement logic is deterministic and unit-tested. The LLM only does the judgement calls: does an
existing tool cover the need, which allowed action fits, and how to explain it. One agent does this as
accurately as two, faster, and is easier to debug. The second agent did not earn its complexity.
