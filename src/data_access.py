from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def _read_csv(name: str) -> pd.DataFrame:
    # keep blank cells as "" instead of NaN
    return pd.read_csv(DATA_DIR / name, keep_default_na=False)


def load_employees() -> pd.DataFrame:
    return _read_csv("employees.csv")


def load_budgets() -> pd.DataFrame:
    return _read_csv("department_budgets.csv")


def load_software_catalog() -> pd.DataFrame:
    return _read_csv("software_catalog.csv")


def load_vendors() -> pd.DataFrame:
    return _read_csv("vendors.csv")


def load_purchase_history() -> pd.DataFrame:
    return _read_csv("purchase_history.csv")


def load_requests() -> list[dict]:
    return json.loads((DATA_DIR / "requests.json").read_text(encoding="utf-8"))


def get_request(request_id: str) -> dict:
    for request in load_requests():
        if request["request_id"] == request_id:
            return request
    raise KeyError(f"Unknown request_id: {request_id}")


def load_policy_text() -> str:
    return (DATA_DIR / "procurement_policy.md").read_text(encoding="utf-8")
