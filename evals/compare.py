"""Run both architectures on the same 10 cases and write evals/results/."""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from run_public_evals import evaluate
from src.solution import handle_request
from src.tools import CLARIFY, ESCALATE, PROCEED, REUSE, ROUTE

sys.stdout.reconfigure(encoding="utf-8")

# expected next action per request, based on the policy
EXPECTED_ACTION = {
    "REQ-1001": [PROCEED],
    "REQ-1002": [ROUTE, REUSE],  
    "REQ-1003": [ROUTE],
    "REQ-1004": [ROUTE],
    "REQ-1005": [ROUTE],
    "REQ-1006": [CLARIFY],
    "REQ-1007": [ESCALATE],
    "REQ-1008": [REUSE],
    "REQ-1009": [ESCALATE],
    "REQ-1010": [PROCEED],
}

OUT = ROOT / "evals" / "results"


def ensure_mock_api():
    try:
        requests.get("http://127.0.0.1:8001/health", timeout=1)
        return None
    except requests.RequestException:
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "mock_api.app:app", "--port", "8001"], cwd=ROOT,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)
        return proc


def ungrounded_numbers(decision) -> list[str]:
    summary = " ".join(e.finding for e in decision.evidence if e.source == "agent_summary")
    facts = " ".join(e.finding for e in decision.evidence if e.source != "agent_summary").replace(",", "")
    bad = []
    for number, k in re.findall(r"\$(\d[\d,.]*)(k?)", summary):
        value = float(number.replace(",", "").rstrip(".")) * (1000 if k else 1)
        if f"{value:.0f}" not in facts:
            bad.append(number + k)
    return bad


def main():
    cases = json.loads((ROOT / "evals" / "public_cases.json").read_text(encoding="utf-8"))
    cases += json.loads((ROOT / "evals" / "extra_cases.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    api = ensure_mock_api()
    rows = []
    try:
        for arch in ("single", "staged"):
            outputs = []
            for case in cases:
                start = time.perf_counter()
                d = handle_request(case["request_id"], architecture=arch)
                ms = (time.perf_counter() - start) * 1000
                failures = evaluate(d, case["expectations"])
                action_ok = d.recommendation in EXPECTED_ACTION[case["request_id"]]
                overrides = sum(e.source == "guardrail" for e in d.evidence)
                bad_numbers = ungrounded_numbers(d)
                rows.append({
                    "case_id": case["case_id"], "request_id": case["request_id"], "architecture": arch,
                    "minimum_checks_passed": not failures, "correct_next_action": action_ok,
                    "recommendation": d.recommendation, "guardrail_overrides": overrides,
                    "ungrounded_numbers": len(bad_numbers), "latency_ms": round(ms),
                    "llm_calls": d.telemetry.llm_calls, "tool_calls": d.telemetry.tool_calls,
                    "failures": " | ".join(failures),
                })
                outputs.append(d.model_dump())
                print(f"{arch:6} {case['case_id']}  checks={'PASS' if not failures else 'FAIL'}  "
                      f"action={'OK' if action_ok else 'WRONG'} ({d.recommendation})  {ms/1000:.1f}s  "
                      f"llm={d.telemetry.llm_calls} tools={d.telemetry.tool_calls}")
            (OUT / f"outputs_{arch}.json").write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    finally:
        if api:
            api.terminate()

    with (OUT / "comparison.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    def stats(arch):
        r = [x for x in rows if x["architecture"] == arch]
        n = len(r)
        return [
            f"{sum(x['minimum_checks_passed'] for x in r)}/{n}",
            f"{sum(x['correct_next_action'] for x in r)}/{n}",
            str(sum(x["guardrail_overrides"] for x in r)),
            str(sum(x["ungrounded_numbers"] for x in r)),
            f"{sum(x['latency_ms'] for x in r) / n / 1000:.1f} s",
            f"{sum(x['llm_calls'] for x in r) / n:.1f}",
            f"{sum(x['tool_calls'] for x in r) / n:.1f}",
        ]

    names = ["Minimum checks passed", "Correct next action", "Guardrail overrides", "Ungrounded $ numbers in summary",
             "Avg latency", "Avg LLM calls", "Avg tool calls"]
    s, b = stats("single"), stats("staged")
    table = "| Metric | A: Single agent | B: Staged 2-agent |\n|---|---:|---:|\n"
    table += "\n".join(f"| {n} | {x} | {y} |" for n, x, y in zip(names, s, b))
    (OUT / "summary.md").write_text("# Comparison results (10 cases, same set for both)\n\n" + table + "\n", encoding="utf-8")
    print("\n" + table)


if __name__ == "__main__":
    main()
