"""Agent tools and the deterministic procurement policy checks."""
from __future__ import annotations

import re
from datetime import date

import requests

from src import data_access
from src.vendor_client import get_vendor_risk as call_vendor_risk_api

REFERENCE_DATE = date(2026, 9, 30)  # policy snapshot date
REVIEW_VALID_DAYS = 365

PROCEED = "Proceed to standard approval"
ROUTE = "Route for specialist review"
REUSE = "Reuse existing tool"
CLARIFY = "Request clarification"
ESCALATE = "Escalate to manual review"
RECOMMENDATIONS = [PROCEED, ROUTE, REUSE, CLARIFY, ESCALATE]

SECURITY_DATA_WORDS = ["source", "confidential", "pii", "credential", "secret", "production"]
SECURITY_INTEGRATION_WORDS = ["production", "cloud", "git", "source"]

INJECTION_PATTERNS = [
    r"ignore\b.{0,30}\b(rules?|instructions?|polic(y|ies)|controls?)",
    r"(treat|mark|consider)\b.{0,40}\bapproved",
    r"approve\b.{0,20}\b(immediately|now|automatically)",
    r"\b(already|pre)[- ]?approved\b",
    r"\b(bypass|disregard|override)\b",
    r"system prompt|you are now|new instructions",
]


def lookup_requester_budget(requester_id: str) -> dict:
    employees = data_access.load_employees()
    match = employees[employees["employee_id"] == requester_id]
    if match.empty:
        return {"found": False, "requester_id": requester_id}
    emp = match.iloc[0].to_dict()
    budgets = data_access.load_budgets()
    b = budgets[budgets["department"] == emp["department"]]
    budget = None if b.empty else {k: int(v) for k, v in b.iloc[0].to_dict().items() if k != "department"}
    return {"found": True, "employee": emp, "department": emp["department"], "budget": budget}


def search_software_catalog(category: str = "", vendor_name: str = "", product_name: str = "") -> dict:
    catalog = data_access.load_software_catalog()
    matches = []
    for row in catalog.to_dict("records"):
        reasons = []
        if vendor_name and row["vendor_name"].lower() == vendor_name.lower():
            reasons.append("same vendor")
        if category and row["category"].lower() == category.lower():
            reasons.append("same category")
        if product_name and row["product_name"].lower() in product_name.lower():
            reasons.append("same product")
        if reasons:
            matches.append({**row, "match_reasons": reasons})
    history = data_access.load_purchase_history()
    past = history[history["vendor_name"].str.lower() == vendor_name.lower()].to_dict("records")
    return {"catalog_matches": matches, "past_purchases_from_vendor": past}


def get_vendor_risk(vendor_name: str) -> dict:
    vendors = data_access.load_vendors()
    reg = vendors[vendors["vendor_name"] == vendor_name]
    registry = None if reg.empty else reg.iloc[0].to_dict()
    try:
        api = {"ok": True, **call_vendor_risk_api(vendor_name)}
    except requests.RequestException as exc:
        api = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"registry": registry, "risk_api": api}


def _days_old(iso_date) -> int | None:
    if not iso_date:
        return None
    return (REFERENCE_DATE - date.fromisoformat(str(iso_date))).days


def approvals_for_amount(cost: float | None) -> list[str]:
    if cost is None:
        return ["Procurement"]
    if cost <= 1000:
        return ["Manager"]
    if cost <= 10000:
        return ["Department Head", "Procurement"]
    if cost <= 25000:
        return ["Department Head", "Finance", "Procurement"]
    return ["Department Head", "Finance", "CFO", "Procurement"]


def find_injection(texts: list[str]) -> list[str]:
    hits = []
    for text in texts:
        for pattern in INJECTION_PATTERNS:
            m = re.search(pattern, text or "", re.IGNORECASE)
            if m:
                hits.append(m.group(0))
    return hits


def check_policy_rules(request: dict) -> dict:
    approvals: list[str] = []
    flags: list[str] = []
    missing: list[str] = []
    evidence: list[dict] = []

    def add(items: list, *values):
        for v in values:
            if v not in items:
                items.append(v)

    def ev(source: str, finding: str, reference: str | None = None):
        evidence.append({"source": source, "finding": finding, "reference": reference})

    cost = request.get("annual_cost_usd")
    data_level = (request.get("data_access_level") or "").lower()
    integrations = request.get("requested_integrations")
    vendor_name = request.get("vendor_name") or ""

    # section 1: required information
    if cost is None:
        add(missing, "annual cost (annual_cost_usd)")
    if not request.get("user_count"):
        add(missing, "number of users/licenses (user_count)")
    if data_level in ("", "unknown"):
        add(missing, "data access level (data_access_level)")
    if integrations is None:
        add(missing, "required integrations (requested_integrations)")
    if not (request.get("business_justification") or "").strip():
        add(missing, "business purpose (business_justification)")
    if not request.get("product_name") or not vendor_name:
        add(missing, "product/vendor name")

    # section 2: budget
    who = lookup_requester_budget(request.get("requester_id", ""))
    if not who["found"]:
        add(missing, "valid requester (employee not found)")
        ev("lookup_requester_budget", f"Requester {request.get('requester_id')} not found in employees.csv")
    elif who["budget"] is None:
        add(missing, f"budget record for department '{who['department']}'")
        add(approvals, "Finance")
        ev("lookup_requester_budget", f"No software budget found for department {who['department']}; budget cannot be verified")
    else:
        avail = who["budget"]["available_usd"]
        name = who["employee"]["name"]
        if cost is None:
            ev("lookup_requester_budget", f"{name} ({who['department']}); available budget ${avail:,} but request cost is missing", "department_budgets.csv")
        elif cost > avail:
            add(flags, "budget_insufficient")
            add(approvals, "Finance")
            ev("lookup_requester_budget", f"Cost ${cost:,} exceeds {who['department']} available budget ${avail:,}", "department_budgets.csv")
        else:
            ev("lookup_requester_budget", f"Cost ${cost:,} is within {who['department']} available budget ${avail:,}", "department_budgets.csv")

    # section 4: approval thresholds
    for a in approvals_for_amount(cost):
        add(approvals, a)
    ev("check_policy_rules", "Cost unknown, approval threshold cannot be set" if cost is None
       else f"Annual amount ${cost:,} -> minimum approvals: {', '.join(approvals_for_amount(cost))}", "Policy section 4")

    # section 3: existing software (same vendor is left for the agent to judge)
    cat = search_software_catalog(request.get("category", ""), vendor_name, request.get("product_name", ""))
    matches = cat["catalog_matches"]
    for m in matches:
        ev("search_software_catalog", f"Existing {m['product_name']} ({m['vendor_name']}, {m['category']}, "
           f"{m['licensed_seats']} seats, scope {m['scope']}, status {m['status']}) - {', '.join(m['match_reasons'])}", m["software_id"])
        if "same category" in m["match_reasons"] and "same vendor" not in m["match_reasons"]:
            add(flags, "existing_tool_overlap")
    if not matches:
        ev("search_software_catalog", "No existing catalog product with the same vendor, category or name")

    # sections 5 and 10: vendor security status
    vendor = get_vendor_risk(vendor_name)
    reg, api = vendor["registry"], vendor["risk_api"]
    needs_security = any(w in data_level for w in SECURITY_DATA_WORDS) or any(
        w in i.lower() for i in (integrations or []) for w in SECURITY_INTEGRATION_WORDS)
    if needs_security:
        ev("check_policy_rules", f"Data access '{data_level}' / integrations {integrations or []} require Security review", "Policy section 5")

    if reg is None:
        new_vendor, legal_ok, reg_status, reg_date = True, False, "", ""
        ev("get_vendor_risk", f"{vendor_name} is not in the vendor registry (new vendor)", "vendors.csv")
    else:
        new_vendor = reg["procurement_status"] != "Approved"
        legal_ok = reg["legal_terms_status"] == "Approved"
        reg_status, reg_date = reg["security_status"].lower(), reg["security_review_date"]
        age = _days_old(reg_date)
        ev("get_vendor_risk", f"Registry: procurement {reg['procurement_status']}, security {reg['security_status']} "
           f"(review date {reg_date or 'none'}{f', {age} days old' if age is not None else ''}), legal terms {reg['legal_terms_status']}",
           reg["vendor_id"])
        if reg_status != "approved" or age is None:
            needs_security = True
        elif age > REVIEW_VALID_DAYS:
            needs_security = True
            add(flags, "vendor_review_expired")

    if api["ok"]:
        api_status, api_date = api.get("security_review_status") or "", api.get("last_review_date") or ""
        age = _days_old(api_date)
        ev("get_vendor_risk", f"Risk API: risk {api.get('risk_level')}, security review {api_status} "
           f"(date {api_date or 'none'}), personal data {api.get('processes_personal_data')}, "
           f"data outside region {api.get('stores_data_outside_region')}", "GET /vendor-risk/" + vendor_name)
        if api_status != "approved" or age is None:
            needs_security = True
        if api_status == "expired" or (age is not None and age > REVIEW_VALID_DAYS):
            needs_security = True
            add(flags, "vendor_review_expired")
        if reg is not None and ((reg_status == "approved") != (api_status == "approved") or (reg_date or "") != api_date):
            needs_security = True
            add(flags, "conflicting_vendor_evidence")
            ev("check_policy_rules", f"Registry says '{reg_status}' ({reg_date or 'no date'}) but risk API says "
               f"'{api_status}' ({api_date or 'no date'}) - not choosing one, routing to Security", "Policy section 5")
        cross_region = api.get("stores_data_outside_region") and any(w in data_level for w in ["pii", "confidential", "source"])
    else:
        needs_security = True
        cross_region = False
        add(flags, "vendor_risk_unavailable")
        ev("get_vendor_risk", f"Risk API unavailable ({api['error'][:120]}); vendor security status NOT verified - not assumed favorable", "Policy section 10")

    if needs_security:
        add(approvals, "Security")
        add(flags, "security_review_required")

    # section 6: privacy
    if "pii" in data_level or cross_region:
        add(approvals, "Privacy")
        add(flags, "privacy_review_required")
        ev("check_policy_rules", "Personal data or sensitive data stored outside region -> Privacy review", "Policy section 6")

    # section 7: legal
    legal_reasons = []
    if new_vendor and cost is not None and cost >= 10000:
        legal_reasons.append("new vendor with spend >= $10,000")
    if not legal_ok:
        legal_reasons.append("legal terms not approved")
    if cross_region:
        legal_reasons.append("cross-region data processing")
    if legal_reasons:
        add(approvals, "Legal")
        add(flags, "legal_review_required")
        ev("check_policy_rules", "Legal review: " + "; ".join(legal_reasons), "Policy section 7")

    # section 9: prompt injection
    texts = [str(request.get(k) or "") for k in ("product_name", "category", "business_justification")]
    texts += [str((reg or {}).get("notes", "")), str(api.get("notes", ""))]
    hits = find_injection(texts)
    if hits:
        add(flags, "prompt_injection_detected")
        ev("check_policy_rules", f"Request/vendor text contains instructions ({'; '.join(hits)}) - ignored as untrusted data", "Policy section 9")

    if missing:
        add(flags, "missing_information")

    specialist = any(a in approvals for a in ("Security", "Privacy", "Legal")) or "budget_insufficient" in flags
    if missing:
        allowed = [CLARIFY]
    elif "vendor_risk_unavailable" in flags or "conflicting_vendor_evidence" in flags:
        allowed = [ESCALATE]
    elif specialist:
        allowed = [ROUTE, REUSE] if matches else [ROUTE]
    else:
        allowed = [PROCEED, REUSE] if matches else [PROCEED]

    return {
        "required_approvals": approvals,
        "risk_flags": flags,
        "missing_information": missing,
        "evidence": evidence,
        "allowed_recommendations": allowed,
        "default_recommendation": allowed[0],
    }


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "lookup_requester_budget",
        "description": "Get the requester's employee record, department and the department's available software budget.",
        "parameters": {"type": "object", "properties": {"requester_id": {"type": "string"}}, "required": ["requester_id"]}}},
    {"type": "function", "function": {
        "name": "search_software_catalog",
        "description": "Find existing approved software with the same vendor, category or product name, plus past purchases from the vendor.",
        "parameters": {"type": "object", "properties": {
            "category": {"type": "string"}, "vendor_name": {"type": "string"}, "product_name": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "get_vendor_risk",
        "description": "Get the vendor's internal registry record AND the external vendor-risk API result (may be unavailable).",
        "parameters": {"type": "object", "properties": {"vendor_name": {"type": "string"}}, "required": ["vendor_name"]}}},
    {"type": "function", "function": {
        "name": "check_policy_rules",
        "description": "Run the deterministic procurement policy checks on this request. Returns the required approvals, "
                       "risk flags, missing information and allowed recommendations. These results are binding.",
        "parameters": {"type": "object", "properties": {}}}},
]


def run_tool(name: str, args: dict, request: dict) -> dict:
    if name == "lookup_requester_budget":
        return lookup_requester_budget(args.get("requester_id", ""))
    if name == "search_software_catalog":
        return search_software_catalog(args.get("category", ""), args.get("vendor_name", ""), args.get("product_name", ""))
    if name == "get_vendor_risk":
        return get_vendor_risk(args.get("vendor_name", ""))
    if name == "check_policy_rules":
        rules = check_policy_rules(request)
        return {k: v for k, v in rules.items() if k != "evidence"}
    return {"error": f"unknown tool {name}"}
