from typing import Literal
from pydantic import BaseModel, Field

class Claim(BaseModel):
    text: str = Field(min_length=10)
    confidence: Literal["high", "medium", "low"]
    source_urls: list[str] = Field(min_length=1)

class Report(BaseModel):
    summary: str = Field(min_length=50)
    claims: list[Claim] = Field(min_length=3)


def render_markdown(topic: str, rep: Report) -> str:
    """Turn the validated object into markdown so the Streamlit UI can still show it."""
    lines = [f"# {topic}", "", "## Summary", rep.summary.strip(), "", "## Key Findings"]
    urls = []
    for i, c in enumerate(rep.claims, 1):
        lines.append(f"{i}. {c.text.strip()} (confidence: **{c.confidence}**)")
        lines.append("   Sources: " + ", ".join(c.source_urls))
        for u in c.source_urls:
            if u not in urls:
                urls.append(u)
    lines += ["", "## Sources"] + [f"- {u}" for u in urls]
    return "\n".join(lines)
