"""A minimal insert gate — the discipline, distilled to run standalone.

This is a clean-room reduction of a real gate I built for a Notion-backed work
queue (production commit e917063 in a private repo). All the private coupling —
the Notion client, database IDs, internal agent names — is stripped. What remains
is the contract that actually matters and the failure modes worth testing:

  create                 the record is new -> write it, leave a receipt
  attach                 a near-duplicate exists -> append to it instead, receipt
  fail-open              the store can't be read -> write the record ANYWAY and
                         FLAG it, because dropping work silently is worse than a dup

The receipt is the point: every write leaves an append-only line, so a monitor can
later spot any record that reached the store WITHOUT going through this gate.
"""
from __future__ import annotations

import datetime as dt
import json


class StoreUnavailable(RuntimeError):
    """Raised by a store client when the existing records can't be read."""


def _norm(text: str) -> set[str]:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(w) >= 4}


def _has_specific_dimension(title: str) -> bool:
    # A match needs >=1 SPECIFIC signal (a digit run), else two generic titles like
    # "catalog dashboard" collapse into one. This mirrors the real gate's rule (a).
    return any(ch.isdigit() for ch in title)


def find_duplicate(title: str, existing: list[dict]) -> dict | None:
    """Return the record `title` duplicates, or None. Precision-first: a false
    merge destroys work, so require strong token overlap AND a specific dimension."""
    cand = _norm(title)
    if not cand or not _has_specific_dimension(title):
        return None
    best, best_overlap = None, 0
    for row in existing:
        overlap = len(cand & _norm(row.get("title", "")))
        if overlap >= 3 and overlap > best_overlap and _has_specific_dimension(row.get("title", "")):
            best, best_overlap = row, overlap
    return best


def submit(record: dict, *, client, existing=None, dry_run: bool = False) -> dict:
    """Resolve the verdict AND perform the write. The only safe entrypoint.

    `client` needs create(record)->id, attach(id, note)->None, and read_existing().
    `existing` lets a caller/test inject the record set (and skip read_existing).
    Returns an outcome dict; every non-dry outcome writes a receipt via client.
    """
    title = (record.get("title") or "").strip()

    if dry_run:
        return {"outcome": "dry_run", "receipt": False}

    # fail-open: if we can't read the store, we can't dedup — so create and say so.
    if existing is None:
        try:
            existing = client.read_existing()
        except StoreUnavailable as exc:
            page_id = client.create(record)
            client.receipt({"action": "created_fail_open", "id": page_id, "error": str(exc)})
            return {"outcome": "created_fail_open", "id": page_id, "error": str(exc),
                    "flagged": True, "receipt": True}

    dup = find_duplicate(title, existing)
    if dup is None:
        page_id = client.create(record)
        client.receipt({"action": "created", "id": page_id})
        return {"outcome": "created", "id": page_id, "receipt": True}

    note = f"restated {dt.date.today().isoformat()}: {title}"
    client.attach(dup["id"], note)
    client.receipt({"action": "attached", "id": dup["id"]})
    return {"outcome": "attached", "id": dup["id"], "receipt": True}


def receipt_line(entry: dict) -> str:
    return json.dumps({"ts": dt.datetime.now(dt.timezone.utc).isoformat(), **entry})
