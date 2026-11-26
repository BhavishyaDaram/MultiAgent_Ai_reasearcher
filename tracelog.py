"""tracelog.py - thread-safe JSONL event log + token / step / cost counters.

Named tracelog (not trace) because Python already has a standard-library
module called `trace`, and a local trace.py would shadow it.
"""
import json
import threading
import time
from datetime import datetime

from config import PRICE_IN_PER_M, PRICE_OUT_PER_M

# Events that count as an agent "step" in the metrics (everything else is just logged).
STEP_EVENTS = {"llm_call", "search", "scrape"}


class Trace:
    def __init__(self, variant: str = "baseline", path: str = "trace.jsonl"):
        self.variant = variant
        self.path = path
        self.t0 = time.time()
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.tokens_in = 0
        self.tokens_out = 0
        self.peak_in = 0          # largest single prompt = the context-window number
        self.llm_calls = 0
        self.steps = 0
        self.estimated = False    # True if any token count had to be estimated
        self.extra = {}           # behaviour metrics: critic_rounds, replanned, ...
        self._lock = threading.Lock()

    def log(self, event: str, **data):
        """Append one event line to trace.jsonl (full detail lives here, not in prompts)."""
        with self._lock:
            if event in STEP_EVENTS:
                self.steps += 1
            record = {
                "run_id": self.run_id,
                "variant": self.variant,
                "t": round(time.time() - self.t0, 2),
                "event": event,
                **data,
            }
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def record_llm(self, name: str, tokens_in: int, tokens_out: int, estimated: bool = False):
        with self._lock:
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out
            self.peak_in = max(self.peak_in, tokens_in)
            self.llm_calls += 1
            self.estimated = self.estimated or estimated
        self.log("llm_call", name=name, tokens_in=tokens_in, tokens_out=tokens_out,
                 estimated=estimated)

    def note(self, **kv):
        """Record behaviour metrics (critic_rounds, replanned, ...) for the results table."""
        with self._lock:
            self.extra.update(kv)

    def summary(self) -> dict:
        cost = (self.tokens_in / 1e6) * PRICE_IN_PER_M + (self.tokens_out / 1e6) * PRICE_OUT_PER_M
        return {
            "variant": self.variant,
            "steps": self.steps,
            "llm_calls": self.llm_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_total": self.tokens_in + self.tokens_out,
            "peak_in": self.peak_in,
            "cost_usd": round(cost, 6),
            "seconds": round(time.time() - self.t0, 2),
            "tokens_estimated": self.estimated,
            **self.extra,
        }
