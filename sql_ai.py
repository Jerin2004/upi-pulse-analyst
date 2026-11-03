"""Natural-language -> SQL with guardrails.

The LLM is untrusted. Defence in depth:
  1. validate_sql(): single SELECT/WITH statement, no write/DDL/PRAGMA/ATTACH keywords, auto LIMIT
  2. read-only SQLite connection (mode=ro)
  3. SQLite authorizer: only SELECT / READ / FUNCTION operations are allowed
  4. progress handler: queries are stopped after a time budget
"""
import json
import os
import re
import sqlite3
import time

import pandas as pd
import requests

from db import SCHEMA_DOC, connect_readonly

ALLOWED_TABLES = {"state_category", "district", "users"}
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|"
    r"analyze|begin|commit|rollback|savepoint|load_extension|truncate)\b", re.I)
MAX_ROWS = 500
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")


class UnsafeSQL(ValueError):
    pass


def validate_sql(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    s = re.sub(r"^```(?:sql)?|```$", "", s, flags=re.I | re.M).strip().rstrip(";").strip()
    if not s:
        raise UnsafeSQL("Empty query.")
    if ";" in s:
        raise UnsafeSQL("Only a single statement is allowed.")
    if "--" in s or "/*" in s:
        raise UnsafeSQL("SQL comments are not allowed in generated queries.")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise UnsafeSQL("Only SELECT queries are allowed.")
    if FORBIDDEN.search(s):
        raise UnsafeSQL("Query contains a forbidden keyword.")
    used = set(re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", s, re.I))
    cte = set(re.findall(r"\b([a-z_][a-z0-9_]*)\s+as\s*\(", s, re.I))
    unknown = {t.lower() for t in used} - ALLOWED_TABLES - {c.lower() for c in cte}
    if unknown:
        raise UnsafeSQL(f"Unknown table(s): {', '.join(sorted(unknown))}")
    if not re.search(r"\blimit\s+\d+\s*$", s, re.I):
        s = f"SELECT * FROM ({s}) LIMIT {MAX_ROWS}"
    return s


def _authorizer(action, *_):
    allowed = {getattr(sqlite3, n) for n in ("SQLITE_SELECT", "SQLITE_READ", "SQLITE_FUNCTION", "SQLITE_RECURSIVE")
               if hasattr(sqlite3, n)}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def run_sql(db_path, sql: str, timeout_s: float = 5.0) -> pd.DataFrame:
    safe = validate_sql(sql)
    con = connect_readonly(db_path)
    con.set_authorizer(_authorizer)
    deadline = time.time() + timeout_s
    con.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10_000)
    try:
        return pd.read_sql(safe, con)
    finally:
        con.close()


SYSTEM_PROMPT = f"""You are a careful analytics SQL assistant for PhonePe Pulse payments data.
{SCHEMA_DOC}
Rules:
- Return ONLY JSON: {{"sql": "...", "explanation": "one or two plain-English sentences"}}
- One SQLite SELECT (CTEs and window functions are fine). No comments, no semicolons.
- Use only the tables above. Use period = '2026-Q2' style strings for quarters; for "latest" use (SELECT MAX(period) FROM <table>).
- For growth use LAG over (PARTITION BY ... ORDER BY year, quarter). Round ratios to 3 decimals.
- If the question cannot be answered from these tables, return {{"sql": "", "explanation": "why"}}."""


def ask_llm(question: str, api_key: str | None = None, history: list | None = None) -> dict:
    api_key = api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, *(history or []), {"role": "user", "content": question}]
    payload = {"model": GROQ_MODEL, "messages": msgs, "temperature": 0,
               "response_format": {"type": "json_object"}}
    if "gpt-oss" in GROQ_MODEL:
        payload["reasoning_effort"] = "low"
    r = requests.post(GROQ_URL, timeout=60, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def answer(question: str, db_path, llm=ask_llm, **kw) -> dict:
    """Returns {sql, explanation, df, error}. `llm` is injectable for tests."""
    out = {"sql": "", "explanation": "", "df": None, "error": None}
    try:
        res = llm(question, **kw)
        out["sql"], out["explanation"] = res.get("sql", ""), res.get("explanation", "")
        if not out["sql"]:
            return out
        out["df"] = run_sql(db_path, out["sql"])
    except UnsafeSQL as e:
        out["error"] = f"Blocked by safety checks: {e}"
    except sqlite3.Error as e:
        out["error"] = f"SQL error: {e}"
    except Exception as e:  # network/LLM problems
        out["error"] = f"{type(e).__name__}: {e}"
    return out
