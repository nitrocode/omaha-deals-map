"""Read new form submissions from the Google Sheet and open one labeled
GitHub Issue per row. Tracks the high-water mark in data/_form_state.json so
the next run resumes where this one left off (idempotent on retries).

Auth assumes Application Default Credentials are already populated by
google-github-actions/auth via Workload Identity Federation. Locally you'd
`gcloud auth application-default login` first.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests
from google.auth import default as google_auth_default
from googleapiclient.discovery import build

from scripts._sheet_to_issues import row_to_issue

SHEET_ID = os.environ["SHEET_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = os.environ["GH_REPO"]  # "nitrocode/omaha-deals-map"

STATE_PATH = Path("data/_form_state.json")
# 8 columns: Timestamp + 7 form questions. Wider in case the form grows
# later; Sheets returns ragged rows so trailing blanks are fine.
SHEET_RANGE = "A:Z"


def load_state() -> dict:
    if not STATE_PATH.exists():
        # First-ever run: skip the header row (row 1) and start from row 2.
        return {"last_processed_row": 1}
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def fetch_rows() -> list[list]:
    creds, _ = google_auth_default(
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=SHEET_RANGE,
    ).execute()
    return resp.get("values", [])


def create_issue(title: str, body: str, labels: list[str]) -> dict:
    r = requests.post(
        f"https://api.github.com/repos/{GH_REPO}/issues",
        headers={
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": title, "body": body, "labels": labels},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    state = load_state()
    last = state.get("last_processed_row", 1)
    rows = fetch_rows()
    if not rows:
        print("[sheet-to-issues] sheet is empty")
        return 0

    # Sheet rows are 1-indexed in the UI; rows[0] is the header (row 1).
    # We iterate with the same 1-indexed numbering so state values match
    # what a human sees if they open the sheet to debug.
    new = [(idx + 1, row) for idx, row in enumerate(rows) if idx + 1 > last]
    if not new:
        print(f"[sheet-to-issues] no new submissions (last_processed_row={last})")
        # Drop a state file on the first-ever empty run so the workflow's
        # commit step has something to look at. We don't bump last_processed_at
        # on empty runs to avoid daily noise commits when nothing's happening.
        if not STATE_PATH.exists():
            save_state(state)
        return 0

    print(f"[sheet-to-issues] processing {len(new)} new submission(s)")
    for row_num, row in new:
        issue = row_to_issue(row)
        if issue is None:
            print(f"  row {row_num}: SKIP (blank or invalid)")
        else:
            created = create_issue(**issue)
            print(f"  row {row_num}: created #{created['number']} {issue['title']}")
        # Stamp progress per-row so a mid-loop crash doesn't re-create earlier
        # issues on the next run.
        state["last_processed_row"] = row_num
        state["last_processed_at"] = datetime.now(UTC).isoformat()
        save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
