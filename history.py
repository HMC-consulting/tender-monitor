import json
import os
from typing import List, Dict, Any

HISTORY_FILE = "seen_tenders.json"


def _make_key(tender: Dict[str, Any]) -> str:
    """
    Create a unique key for a tender based on URL + title.
    This is what we use to detect duplicates across days.
    """
    url = (tender.get("url") or "").strip().lower()
    title = (tender.get("title") or "").strip().lower()
    return f"{url}||{title}"


def load_history() -> Dict[str, Dict[str, Any]]:
    """
    Load the seen tenders history from JSON.
    Returns a dict mapping key -> tender metadata.
    """
    if not os.path.exists(HISTORY_FILE):
        return {}

    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
            # Expecting { key: tender_dict }
            if isinstance(data, dict):
                return data
            else:
                return {}
    except Exception:
        # If file is corrupted or unreadable, start fresh
        return {}


def save_history(history: Dict[str, Dict[str, Any]]) -> None:
    """
    Save the history dict back to JSON.
    """
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def filter_new_tenders(
    tenders: List[Dict[str, Any]],
    history: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Given a list of tender dicts and an existing history,
    return only the new tenders and update history in-memory.

    A tender is considered duplicate if URL + title match
    an entry already in history.
    """
    new_tenders = []

    for t in tenders:
        key = _make_key(t)
        if not key:
            # If we can't build a key, treat as new but don't store
            new_tenders.append(t)
            continue

        if key in history:
            # already seen, skip
            continue

        # Mark as new, and store in history
        new_tenders.append(t)
        history[key] = {
            "source": t.get("source"),
            "title": t.get("title"),
            "url": t.get("url"),
        }

    return new_tenders
