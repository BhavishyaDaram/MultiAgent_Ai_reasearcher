"""pipeline.py - the research pipeline with optional agentic extensions.

Run:  python pipeline.py "topic" [--planner] [--critic] [--compact] [--schema] [--multi]
Each flag adds one idea; with no flags you get the baseline pipeline.
"""
import difflib
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime

from pydantic import ValidationError

from agents import (as_str_list, critic_json_prompt, critic_prompt, extract_prompt,
                    parse_json_any, plan_prompt, replan_prompt, run_chain,
                    schema_prompt, to_text, writer_prompt)
from config import Flags, parse_cli, variant_name
from notes import Note, add_notes, format_notes
from schemas import Report, render_markdown
from tools import scrape_url, web_search
from tracelog import Trace

MAX_SUBQ = 4            # planner output cap
MAX_CRITIC_ROUNDS = 2   # critique -> follow-up -> redraft, at most this many times
MAX_FOLLOWUPS = 3       # targeted searches per critic round
MAX_SCHEMA_TRIES = 3    # first attempt + 2 retries with the validation error fed back


# ---------------------------------------------------------------------------
# Tools (called directly: the old agents only ever made one tool call each)
# ---------------------------------------------------------------------------

def search(query: str, trace: Trace) -> str:
    try:
        out = to_text(web_search.invoke(query))
    except Exception:
        try:
            out = to_text(web_search.invoke({"query": query}))
        except Exception as e:
            out = ""
            trace.log("search_error", query=query, error=str(e)[:200])
    trace.log("search", query=query, chars=len(out))
    return out


def parse_search(out: str) -> list:
    """Pull {title, url} pairs out of the web_search tool output."""
    results = []
    for block in out.split("\n---\n"):
        m = re.search(r"^URL:\s*(\S+)", block, re.M)
        if m:
            t = re.search(r"^Title:\s*(.+)$", block, re.M)
            results.append({"title": t.group(1).strip() if t else "", "url": m.group(1)})
    return results


def scrape(url: str) -> str:
    try:
        return to_text(scrape_url.invoke(url))
    except Exception:
        try:
            return to_text(scrape_url.invoke({"url": url}))
        except Exception as e:
            return f"Could not scrape URL: {e}"


class Shared:
    """State shared by researcher instances. The lock makes 'claim this URL' atomic,
    so two parallel researchers never read the same page."""

    def __init__(self):
        self.seen = set()
        self.lock = threading.Lock()

    def claim_url(self, url: str) -> bool:
        with self.lock:
            if url in self.seen:
                return False
            self.seen.add(url)
            return True


# ---------------------------------------------------------------------------
# Planning (--planner) and re-planning
# ---------------------------------------------------------------------------

def plan(topic: str, trace: Trace) -> list:
    raw = run_chain(plan_prompt, {"topic": topic}, trace, "plan")
    obj = parse_json_any(raw)
    subqs = as_str_list(obj)[:MAX_SUBQ] if isinstance(obj, list) else []
    subqs = subqs or [topic]
    trace.log("plan", sub_questions=subqs)
    return subqs


def replan(topic: str, notes: list, remaining: list, trace: Trace):
    """One chance to revise the remaining sub-questions after seeing early findings."""
    raw = run_chain(replan_prompt, {
        "topic": topic,
        "notes": format_notes(notes)[:4000] or "(none)",
        "remaining": "\n".join(f"- {q}" for q in remaining),
    }, trace, "replan")
    obj = parse_json_any(raw)
    if (isinstance(obj, dict) and obj.get("changed") is True
            and isinstance(obj.get("sub_questions"), list)):
        new = as_str_list(obj["sub_questions"])[:3]
        changed = new != remaining
    else:
        new, changed = remaining, False
    trace.log("replan", changed=changed, before=remaining, after=new)
    trace.note(replanned=int(changed))
    return new


# ---------------------------------------------------------------------------
# Researcher: search + read + extract notes for ONE sub-question
# ---------------------------------------------------------------------------

def research(subq, topic, flags, trace, shared, on_search_done=None) -> dict:
    notes, blocks = [], []
    search_text = search(subq, trace)
    if on_search_done:
        on_search_done()
    read = 0
    for r in parse_search(search_text):
        if read >= flags.max_urls:
            break
        url = r["url"]
        if not shared.claim_url(url):
            trace.log("url_skipped_duplicate", url=url, subq=subq)
            continue
        text = scrape(url)
        ok = not text.startswith("Could not scrape URL") and len(text) >= 200
        # The FULL page goes to the trace log only; prompts get notes/summary/raw per flags.
        trace.log("scrape", url=url, chars=len(text), ok=ok, subq=subq, text=text)
        if not ok:
            continue
        read += 1
        raw = run_chain(extract_prompt, {"topic": topic, "subq": subq, "url": url,
                                         "text": text[:6000]}, trace, "extract")
        obj = parse_json_any(raw)
        summary, claims = "", []
        if isinstance(obj, dict):
            summary = str(obj.get("summary", "")).strip()
            claims = as_str_list(obj.get("claims"))
        elif isinstance(obj, list):
            claims = as_str_list(obj)
        add_notes(notes, [Note(claim=c, url=url, subq=subq) for c in claims])
        # COMPACTION: with --compact the raw page is dropped from working memory.
        blocks.append({"url": url, "summary": summary,
                       "raw": "" if flags.compact else text})
    return {"subq": subq, "search": search_text, "notes": notes, "blocks": blocks}


def safe_research(*args, **kwargs) -> dict:
    """A failing researcher must not kill the whole run."""
    try:
        return research(*args, **kwargs)
    except Exception as e:
        trace = args[3]
        trace.log("research_error", subq=args[0], error=str(e)[:300])
        return {"subq": args[0], "search": "", "notes": [], "blocks": []}


def merge(result: dict, notes: list, blocks: list, searches: list) -> int:
    """Merge one researcher's output into the supervisor's shared notes. Returns #new notes."""
    if result["search"]:
        searches.append(result["search"])
    blocks.extend(result["blocks"])
    return add_notes(notes, result["notes"])


# ---------------------------------------------------------------------------
# Writing: free text, or a validated structure (--schema)
# ---------------------------------------------------------------------------

def build_context(notes, blocks, searches, flags: Flags) -> str:
    parts = ["NUMBERED NOTES:\n" + (format_notes(notes) or "(none)")]
    if flags.compact and notes:
        summaries = "\n".join(f"- {b['url']}: {b['summary']}" for b in blocks if b["summary"])
        parts.append("SOURCE SUMMARIES:\n" + (summaries or "(none)"))
    else:
        parts.append("SEARCH RESULTS:\n" + "\n\n".join(searches))
        raw = "\n\n".join(f"URL: {b['url']}\n{b['raw'] or b['summary']}" for b in blocks)
        parts.append("RAW SOURCE TEXT:\n" + raw)
    return "\n\n".join(parts)


def write_structured(topic, research_text, notes, trace, previous=None, issues=None):
    """Ask for JSON, validate with Pydantic + a source check, retry with the error."""
    allowed = {n.url for n in notes}
    error = "None"
    for attempt in range(MAX_SCHEMA_TRIES):
        raw = run_chain(schema_prompt, {
            "topic": topic, "research": research_text,
            "previous_draft": previous or "None", "issues": issues or "None",
            "validation_error": error,
        }, trace, "write_schema")
        try:
            obj = parse_json_any(raw)
            if not isinstance(obj, dict):
                raise ValueError("Output was not a JSON object")
            rep = Report.model_validate(obj)
            bad = sorted({u for c in rep.claims for u in c.source_urls if u not in allowed})
            if bad:
                raise ValueError(f"These source_urls do not appear in the notes: {bad[:3]}")
            return rep, attempt
        except (ValidationError, ValueError) as e:
            error = str(e)[:600]
            trace.log("schema_retry", attempt=attempt, error=error)
    raise RuntimeError("schema validation failed after retries")


def draft_report(topic, notes, blocks, searches, flags, trace, previous=None, issues=None):
    """Returns (markdown, report_json_or_None)."""
    context = build_context(notes, blocks, searches, flags)
    if flags.schema:
        try:
            rep, retries = write_structured(topic, context, notes, trace, previous, issues)
            trace.note(schema_retries=trace.extra.get("schema_retries", 0) + retries)
            return render_markdown(topic, rep), rep.model_dump()
        except RuntimeError:
            trace.note(schema_failed=1)  # fall back to free text so the run still finishes
    md = run_chain(writer_prompt, {
        "topic": topic, "research": context,
        "previous_draft": previous or "None", "issues": issues or "None",
    }, trace, "write")
    return md, None


# ---------------------------------------------------------------------------
# Critique (--critic)
# ---------------------------------------------------------------------------

def critique(report_md: str, notes: list, trace: Trace):
    raw = run_chain(critic_json_prompt,
                    {"report": report_md, "notes": format_notes(notes) or "(none)"},
                    trace, "critic_json")
    obj = parse_json_any(raw)
    if not isinstance(obj, dict):
        return [], []
    return as_str_list(obj.get("unsupported_claims")), as_str_list(obj.get("contradictions"))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_research_pipeline(topic: str, status_callback=None, flags: Flags = None) -> dict:
    """
    Returns a dict with: search_results, scraped_content, report, feedback (used by
    app.py) plus notes, plan, report_json and metrics.
    """
    flags = flags or Flags()
    trace = Trace(variant=variant_name(flags))
    trace.log("run_start", topic=topic, flags=asdict(flags))

    def notify(stage: str):  # only ever called from the main thread (Streamlit-safe)
        if status_callback:
            status_callback(stage)

    shared = Shared()
    notes, blocks, searches = [], [], []

    # ---- Phase 1: plan + research -------------------------------------------------
    notify("search")
    use_plan = flags.planner or flags.multi
    subqs = plan(topic, trace) if use_plan else [topic]
    print(f"\n[Plan] {subqs}")

    if flags.multi and len(subqs) > 1:
        # Supervisor: dispatch every sub-question at once. The price of parallelism is
        # that nobody can re-plan from early findings, because all of them start together.
        notify("read")
        with ThreadPoolExecutor(max_workers=min(3, len(subqs))) as pool:
            futures = [pool.submit(safe_research, q, topic, flags, trace, shared)
                       for q in subqs]
            for f in futures:
                merge(f.result(), notes, blocks, searches)
    else:
        read_notified = {"done": False}

        def first_search_done():
            if not read_notified["done"]:
                read_notified["done"] = True
                notify("read")

        remaining, replanned = list(subqs), False
        while remaining:
            q = remaining.pop(0)
            merge(safe_research(q, topic, flags, trace, shared, first_search_done),
                  notes, blocks, searches)
            if flags.planner and not replanned and remaining:
                remaining = replan(topic, notes, remaining, trace)
                replanned = True
    trace.note(n_notes=len(notes), n_pages=len(blocks), n_subq=len(subqs))
    print(f"[Research] {len(notes)} notes from {len(blocks)} pages")

    # ---- Phase 2: write -----------------------------------------------------------
    notify("write")
    report_md, report_json = draft_report(topic, notes, blocks, searches, flags, trace)
    first_draft = report_md
    print("\nDraft report:\n", report_md)

    # ---- Phase 3: critique loop, then the original score-only critic -------------------
    notify("critic")
    if flags.critic:
        revisions = 0
        for rnd in range(MAX_CRITIC_ROUNDS):
            unsupported, contradictions = critique(report_md, notes, trace)
            trace.log("critic_round", round=rnd, unsupported=unsupported,
                      contradictions=contradictions)
            if not unsupported and not contradictions:
                break
            added = 0
            for claim in unsupported[:MAX_FOLLOWUPS]:  # targeted follow-up searches
                added += merge(safe_research(claim, topic, flags, trace, shared),
                               notes, blocks, searches)
            issues = "\n".join(
                [f"- Unsupported claim (remove or support): {c}" for c in unsupported]
                + [f"- Contradiction to resolve or flag: {c}" for c in contradictions])
            report_md, report_json = draft_report(topic, notes, blocks, searches, flags,
                                                  trace, previous=report_md, issues=issues)
            revisions += 1
            trace.log("redraft", round=rnd, new_notes=added)
        change = 1 - difflib.SequenceMatcher(None, first_draft, report_md).ratio()
        trace.note(critic_rounds=revisions, critic_change=round(change, 3))

    feedback = run_chain(critic_prompt, {"report": report_md}, trace, "critic_score")
    print("\nFinal report:\n", report_md, "\n\nCritic score:\n", feedback)

    # ---- Result (keys used by app.py are unchanged) -------------------------------------
    state = {
        "search_results": "\n\n".join(searches) or "No search results.",
        "scraped_content": "\n\n".join(
            f"URL: {b['url']}\n{(b['raw'][:1500] or b['summary'])}" for b in blocks
        ) or "No pages could be scraped.",
        "report": report_md,
        "feedback": feedback,
        "notes": [asdict(n) for n in notes],
        "plan": subqs,
        "report_json": report_json,
    }
    state["metrics"] = trace.summary()
    trace.log("run_end", **state["metrics"])
    print("\nMetrics:", state["metrics"])
    return state


if __name__ == "__main__":
    topic, flags = parse_cli()
    topic = topic or input("\nEnter a research topic: ")
    result = run_research_pipeline(topic, flags=flags)

    os.makedirs("runs", exist_ok=True)
    fname = f"runs/{datetime.now():%Y%m%d-%H%M%S}_{variant_name(flags)}.md"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"# {topic}\n\n{result['report']}\n\n---\n{result['feedback']}\n")
    print("Saved:", fname)
