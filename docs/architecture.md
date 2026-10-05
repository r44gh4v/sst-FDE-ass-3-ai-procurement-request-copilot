# Architecture and workflow

## Workflow (both architectures)

```mermaid
flowchart TD
    R[Purchase request<br/>untrusted data] --> RULES
    subgraph CODE [Code - deterministic]
      RULES[check_policy_rules<br/>budget, thresholds, overlap,<br/>vendor status, privacy, legal,<br/>missing info, injection scan]
    end
    R --> AGENT
    subgraph AI [AI - interpret and recommend]
      AGENT[Architecture A or B<br/>see below]
    end
    AGENT -- tool calls --> T1[lookup_requester_budget]
    AGENT -- tool calls --> T2[search_software_catalog]
    AGENT -- tool calls --> T3[get_vendor_risk<br/>registry + mock API]
    AGENT -- tool calls --> RULES
    RULES --> MERGE
    AGENT -- "JSON: recommendation,<br/>summary, next_step, extra flags" --> MERGE
    MERGE[finalize: guardrail merge<br/>code keeps approvals, flags, missing info<br/>LLM choice must be in allowed list] --> OUT[ProcurementDecision]
    OUT --> UI[Streamlit UI<br/>request, evidence, recommendation]
    UI --> H[Human: send to approvers /<br/>return to requester / reject]
```

## Architecture A - single agent

```mermaid
flowchart LR
    Q[Request] --> A1[Agent with 4 tools<br/>loop: call LLM, run tools, repeat<br/>max 6 turns]
    A1 --> J[final JSON] --> G[guardrail merge]
```

## Architecture B - staged, 2 agents

```mermaid
flowchart LR
    Q[Request] --> R1[Agent 1: Researcher<br/>3 data tools, no decision]
    R1 -- research notes JSON --> R2[Agent 2: Reviewer<br/>no tools]
    P[check_policy_rules output] -- handoff --> R2
    R2 --> J[final JSON] --> G[guardrail merge]
```

Handoff format from Agent 1 to Agent 2: `{"facts": [...], "overlap_notes": "...", "concerns": [...]}`
plus the rule results `{required_approvals, risk_flags, missing_information, allowed_recommendations}`.

## Who decides what

| Decision | Owner | Why |
|---|---|---|
| Approval thresholds, budget check, review dates (365 days from 2026-09-30) | Code | Must be exact and repeatable |
| Security / Privacy / Legal triggers, registry-vs-API conflict, API outage | Code | Policy rules, no judgement needed |
| Missing required fields, prompt-injection pattern scan | Code | Cheap and reliable |
| Does an existing tool already cover the need? | LLM | Needs reading the justification |
| Which allowed recommendation fits, summary, next step wording | LLM | Interpretation |
| Approve, buy, budget exceptions, override reviews | Human | Policy section 11 |

## Stop / escalation conditions

- Missing required info -> only `Request clarification` is allowed.
- Vendor-risk API down or registry and API disagree -> `Escalate to manual review` (or route), plus Security.
- Any Security/Privacy/Legal/Finance-exception trigger -> `Proceed` is not allowed.
- LLM fails (no key, timeout, rate limit) -> rules-only decision, noted in the evidence.
- Agent loop is capped at 6 LLM turns.
- `human_review_required` is always `true`.

## Intentionally not built

- No agent framework (LangChain etc.): one short loop is easier to read and debug.
- No vector search: the catalog is 10 rows, so exact vendor/category matching is enough.
- No database or login: the human action log is a local `review_log.jsonl` file.
- No more than 2 agents (brief's recommended maximum).
