"""config.py - feature flags, CLI parsing and cost constants shared by every module."""
import argparse
import os
from dataclasses import dataclass, fields


@dataclass
class Flags:
    planner: bool = False   # plan sub-questions first, research each, allow ONE re-plan
    critic: bool = False    # generate -> critique -> targeted follow-up search -> redraft
    compact: bool = False   # keep page SUMMARIES in context instead of raw page text
    schema: bool = False    # final answer is a Pydantic-validated list of claims
    multi: bool = False     # supervisor dispatches sub-questions to parallel researchers
    max_urls: int = 3       # pages read per search call


def variant_name(flags: Flags) -> str:
    """'baseline' if no flag is on, else e.g. 'planner+critic'."""
    active = [f.name for f in fields(flags)
              if f.name != "max_urls" and getattr(flags, f.name)]
    return "+".join(active) if active else "baseline"


def parse_cli():
    """Returns (topic, Flags). Topic is None if not given on the command line."""
    p = argparse.ArgumentParser(description="Multi-agent research assistant")
    p.add_argument("topic", nargs="?", default=None)
    p.add_argument("--planner", action="store_true", help="plan sub-questions first")
    p.add_argument("--critic", action="store_true", help="critique + targeted follow-up")
    p.add_argument("--compact", action="store_true", help="compress older tool results")
    p.add_argument("--schema", action="store_true", help="validated structured output")
    p.add_argument("--multi", action="store_true", help="parallel researcher agents")
    p.add_argument("--max-urls", type=int, default=3, help="pages read per search")
    a = p.parse_args()
    flags = Flags(planner=a.planner, critic=a.critic, compact=a.compact,
                  schema=a.schema, multi=a.multi, max_urls=a.max_urls)
    return a.topic, flags


# Used only to turn token counts into an approximate dollar figure for the results
# table. EDIT these to the current Gemini price per 1M tokens for the model you use.
PRICE_IN_PER_M = float(os.getenv("PRICE_IN_PER_M", "0.10"))
PRICE_OUT_PER_M = float(os.getenv("PRICE_OUT_PER_M", "0.40"))
