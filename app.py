from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.solution import analyze_request

ROOT = Path(__file__).resolve().parent
REQUESTS = json.loads((ROOT / "data" / "requests.json").read_text(encoding="utf-8"))
BY_ID = {r["request_id"]: r for r in REQUESTS}
REVIEW_LOG = ROOT / "review_log.jsonl"


def md(text: str) -> str:
    return str(text).replace("$", "\\$")


st.set_page_config(page_title="Procurement Request Copilot", layout="wide")
st.title("AI Procurement Request Copilot")
st.caption("Gathers evidence and recommends a next step. It never approves or buys anything - humans decide.")

request_id = st.sidebar.selectbox(
    "Request", list(BY_ID.keys()), format_func=lambda rid: f"{rid} - {BY_ID[rid]['product_name']}"
)
architecture = st.sidebar.radio(
    "Architecture", ["single", "staged"], horizontal=True,
    help="single = one agent with tools. staged = research agent -> review agent.",
)

left, right = st.columns([0.9, 1.1], gap="large")

with left:
    st.subheader("1. Request details")
    st.caption("You can edit the JSON to try your own request.")
    text = st.text_area("Request", json.dumps(BY_ID[request_id], indent=2), height=420, key=request_id,
                        label_visibility="collapsed")
    run = st.button("Analyze request", type="primary", use_container_width=True)

if run:
    try:
        req = json.loads(text)
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON: {exc}")
        st.stop()
    with st.spinner("Agent is gathering evidence..."):
        st.session_state["result"] = (text, architecture, analyze_request(req, architecture))

with right:
    saved = st.session_state.get("result")
    result = saved[2] if saved and saved[:2] == (text, architecture) else None
    if result is None:
        st.info("Pick a request and click **Analyze request**.")
        st.stop()

    st.subheader("2. Recommendation")
    st.markdown(f"### {result.recommendation}")
    st.markdown("**Next step:** " + md(result.next_step))

    c1, c2, c3 = st.columns(3)
    c1.markdown("**Approvals required**\n\n" + "\n".join(f"- {a}" for a in result.required_approvals))
    c2.markdown("**Risk flags**\n\n" + ("\n".join(f"- {f}" for f in result.risk_flags) or "None"))
    c3.markdown("**Missing information**\n\n" + ("\n".join(f"- {m}" for m in result.missing_information) or "None"))

    st.subheader("3. Evidence")
    for e in result.evidence:
        ref = f" *(ref: {e.reference})*" if e.reference else ""
        st.markdown(f"- **{e.source}**: {md(e.finding)}{md(ref)}")
    t = result.telemetry
    st.caption(f"LLM calls: {t.llm_calls} | Tool calls: {t.tool_calls} ({', '.join(t.tool_names)})")

    st.subheader("4. Human action")
    reviewer = st.text_input("Your name (reviewer)")
    note = st.text_input("Note (optional)")
    a1, a2, a3 = st.columns(3)
    action = None
    if a1.button("Send to approvers", use_container_width=True):
        action = "sent_to_approvers"
    if a2.button("Return to requester", use_container_width=True):
        action = "returned_to_requester"
    if a3.button("Reject", use_container_width=True):
        action = "rejected"
    if action:
        if not reviewer.strip():
            st.warning("Enter your name so the decision is traceable.")
        else:
            entry = {"time": datetime.now().isoformat(timespec="seconds"), "request_id": result.request_id,
                     "copilot_recommendation": result.recommendation, "human_action": action,
                     "reviewer": reviewer.strip(), "note": note}
            with REVIEW_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            st.success(f"Logged: {action} by {reviewer} (review_log.jsonl)")
