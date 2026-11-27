import json
import os
import re
import time

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from tools import web_search, scrape_url

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-flash-lite-latest")


def make_llm(name: str = None):
    return ChatGoogleGenerativeAI(
        model=name or MODEL_NAME,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )


llm = make_llm()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_text(content) -> str:
    """Gemini sometimes returns a list of content blocks instead of a string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "".join(parts)
    return str(content)


_RETRY_WORDS = ("429", "quota", "rate", "503", "unavailable", "timeout",
                "overloaded", "resource")


def _retryable(e: Exception) -> bool:
    s = str(e).lower()
    return any(w in s for w in _RETRY_WORDS)


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(5),
       wait=wait_exponential(multiplier=2, min=2, max=40), reraise=True)
def invoke_llm(model, messages):
    """One LLM call with automatic back-off on rate-limit / overload errors."""
    msg = model.invoke(messages)
    delay = float(os.getenv("LLM_DELAY", "0"))
    if delay:
        time.sleep(delay)
    return msg


def run_chain(prompt, inputs: dict, trace=None, name: str = "llm", model=None) -> str:
    """Render a prompt, call the LLM, record tokens in the trace, return plain text."""
    messages = prompt.format_messages(**inputs)
    msg = invoke_llm(model or llm, messages)
    text = to_text(msg.content)
    if trace:
        usage = getattr(msg, "usage_metadata", None) or {}
        tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        estimated = False
        if not (tin or tout):  # provider gave no usage: estimate ~4 characters per token
            prompt_text = "\n".join(to_text(m.content) for m in messages)
            tin, tout, estimated = len(prompt_text) // 4, len(text) // 4, True
        trace.record_llm(name, tin, tout, estimated)
    return text


def parse_json_any(text: str):
    """Parse a JSON object or list out of an LLM reply (handles ``` fences and chatter)."""
    cleaned = re.sub(r"```(?:json)?", "", text or "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    spans = []
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s, e = cleaned.find(open_c), cleaned.rfind(close_c)
        if s != -1 and e > s:
            spans.append((s, e))
    for s, e in sorted(spans):  # trying whichever bracket appears first
        try:
            return json.loads(cleaned[s:e + 1])
        except json.JSONDecodeError:
            continue
    return None


def as_str_list(x) -> list:
    """Normalise whatever the model returned into a clean list of non-empty strings."""
    if not isinstance(x, list):
        return []
    out = []
    for item in x:
        if isinstance(item, str):
            s = item
        elif isinstance(item, dict):
            s = next((str(item[k]) for k in ("query", "question", "claim", "text")
                      if k in item), "")
        else:
            s = str(item)
        if s.strip():
            out.append(s.strip())
    return out


# ---------------------------------------------------------------------------
# Original agent builders (kept for reference; the pipeline now calls the two
# tools directly, which saves one LLM round-trip per search/scrape)
# ---------------------------------------------------------------------------

def build_search_agent():
    return create_agent(model=llm, tools=[web_search])


def build_reader_agent():
    return create_agent(model=llm, tools=[scrape_url])


# ---------------------------------------------------------------------------
# Prompts. NOTE: no literal curly braces inside templates - only {placeholders}.
# ---------------------------------------------------------------------------

writer_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an expert research writer. Write clear, structured and insightful reports."),
    ("human",
     """Write a detailed research report on the topic below.

Topic: {topic}

Research Gathered (numbered notes first, then supporting material):
{research}

Previous draft (only present when revising, otherwise None):
{previous_draft}

Issues to fix (only present when revising, otherwise None):
{issues}

Structure the report as:
- Introduction
- Key Findings (minimum 3 well-explained points)
- Conclusion
- Sources (list all URLs found in the research)

Cite the numbered notes inline, like [1] or [2][3], after the claims they support.
Only state facts that the research supports. If a previous draft and issues are given,
revise the draft so that every issue is fixed (remove or soften claims that cannot be supported).

Be detailed, factual and professional."""),
])

writer_chain = writer_prompt | llm | StrOutputParser()


critic_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a sharp and constructive research critic. Be honest and specific."),
    ("human",
     """Review the research report below and evaluate it strictly.

Report:
{report}

Respond in this exact format:

Score: X/10

Strengths:
- ...
- ...

Areas to Improve:
- ...
- ...

One line verdict:
..."""),
])

critic_chain = critic_prompt | llm | StrOutputParser()


extract_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You extract precise, self-contained factual claims from web page text."),
    ("human",
     """Overall topic: {topic}
Sub-question being researched: {subq}
Source URL: {url}

Page text:
{text}

Read the page and return ONLY a JSON object with two keys:
"summary": a summary of the page in at most 60 words, focused on the sub-question
"claims": a list of 3 to 5 factual claims from this page relevant to the sub-question.
Each claim must be one self-contained sentence, include concrete details (numbers, names,
dates) when present, and use only information that is in the page text.
No markdown, no commentary."""),
])


plan_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a research planner who breaks questions into searchable parts."),
    ("human",
     """Question: {topic}

Break this question into 3 sub-questions (at most 4) that together fully answer it.
Each sub-question must be a standalone query that works as a web search, and the
sub-questions must not overlap.
Return ONLY a JSON list of strings."""),
])


replan_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a research planner who adapts the plan to what has been found."),
    ("human",
     """Original question: {topic}

Notes found so far:
{notes}

Sub-questions still to research:
{remaining}

Decide whether the remaining sub-questions are still the right ones. Change them only if
the notes show that one is already answered, is irrelevant, or that an important gap exists.
Return ONLY a JSON object with two keys:
"changed": true or false
"sub_questions": the list (at most 3) of sub-questions still to research, revised, replaced
or shortened as needed. Use the original list if changed is false."""),
])


critic_json_prompt = ChatPromptTemplate.from_messages([
    ("system", "You verify research reports against evidence. Be strict and literal."),
    ("human",
     """Report to check:
{report}

Evidence notes (the only allowed evidence):
{notes}

Check every factual claim in the report against the notes.
Return ONLY a JSON object with two keys:
"unsupported_claims": a list of claims in the report that no note supports. Write each as a
short, search-ready query that could find evidence for it.
"contradictions": a list of short descriptions of notes or claims that contradict each other.
Use empty lists when there are none."""),
])


schema_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert research writer who outputs strictly valid JSON."),
    ("human",
     """Topic: {topic}

Research gathered (numbered notes first, then supporting material):
{research}

Previous draft (only present when revising, otherwise None):
{previous_draft}

Issues to fix (only present when revising, otherwise None):
{issues}

Validation error from your last attempt (otherwise None):
{validation_error}

Return ONLY a JSON object with exactly two keys:
"summary": a synthesized summary of at least 80 words
"claims": a list of at least 3 claim objects. Each claim object has the keys
"text" (one full sentence), "confidence" (exactly one of "high", "medium", "low") and
"source_urls" (a non-empty list of URLs copied exactly from the source lines of the notes).
Use only facts from the notes. Rate confidence "high" only when two or more notes agree.
No markdown fences, no commentary."""),
])


judge_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a strict, impartial grader of research answers."),
    ("human",
     """Question:
{question}

Evidence the agent collected (claims with their source URLs):
{evidence}

Answer to grade:
{report}

Score the answer on two criteria, each an integer from 1 to 5:
"correctness": 5 = accurate, complete and directly answers the question; 3 = partly correct
or missing important parts; 1 = wrong, off-topic or mostly unsupported.
"citations": 5 = key claims are tied to sources that appear in the evidence; 3 = some claims
are cited; 1 = no usable citations or citations not found in the evidence.
Return ONLY a JSON object with the keys "correctness", "citations" and "reason"
(one sentence)."""),
])
