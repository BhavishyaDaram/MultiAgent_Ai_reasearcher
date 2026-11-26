"""notes.py - the shared, durable memory of the agent: a list of Notes."""
from dataclasses import dataclass


@dataclass
class Note:
    claim: str   # one factual statement
    url: str     # page it came from
    subq: str    # sub-question it answers (the topic itself when no planner)


def add_notes(notes: list, new: list) -> int:
    """Append notes, skipping duplicates (same url + same claim). Returns #added."""
    seen = {(n.url, n.claim.strip().lower()) for n in notes}
    added = 0
    for n in new:
        key = (n.url, n.claim.strip().lower())
        if key not in seen:
            seen.add(key)
            notes.append(n)
            added += 1
    return added


def format_notes(notes: list) -> str:
    """Numbered text block that the writer and the critic read: [1] claim (source: url)."""
    return "\n".join(f"[{i}] {n.claim} (source: {n.url})"
                     for i, n in enumerate(notes, 1))
