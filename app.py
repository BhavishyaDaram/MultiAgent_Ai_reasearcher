"""
AI Multi-Agent Research Assistant — UI layer.

This file only redesigns the presentation layer. All research logic lives in
pipeline.run_research_pipeline(topic, status_callback) and is unchanged:

    result = run_research_pipeline(clean_topic, status_callback=on_stage)
    result = {
        "search_results": ...,
        "scraped_content": ...,
        "report": ...,
        "feedback": ...,
    }
"""

import streamlit as st
import streamlit.components.v1 as components

from pipeline import run_research_pipeline

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Research Intelligence — Multi-Agent AI",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Pipeline stage metadata (single source of truth for order + copy)
# ---------------------------------------------------------------------------
STAGE_ORDER = ["search", "read", "write", "critic"]

STAGE_INFO = {
    "search": {
        "label": "Search Agent",
        "desc": "Finding recent and reliable sources",
        "icon": "S",
    },
    "read": {
        "label": "Reader Agent",
        "desc": "Extracting content from the top source",
        "icon": "R",
    },
    "write": {
        "label": "Writer",
        "desc": "Synthesizing findings into a report",
        "icon": "W",
    },
    "critic": {
        "label": "Critic",
        "desc": "Reviewing the report for quality",
        "icon": "C",
    },
}

EXAMPLE_TOPICS = [
    "Generative AI in Healthcare",
    "Future of AI Agents",
    "Quantum Computing",
    "AI in Cybersecurity",
]

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "result" not in st.session_state:
    st.session_state.result = None
if "topic" not in st.session_state:
    st.session_state.topic = ""
if "error" not in st.session_state:
    st.session_state.error = None
if "topic_input" not in st.session_state:
    st.session_state.topic_input = ""
if "agent_status" not in st.session_state:
    st.session_state.agent_status = {s: "waiting" for s in STAGE_ORDER}
if "is_running" not in st.session_state:
    st.session_state.is_running = False


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
def inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        :root {
            --bg: #0b0d12;
            --bg-elevated: #12151c;
            --card: #151922;
            --card-border: #232733;
            --text-primary: #e9ebf1;
            --text-secondary: #9aa1b1;
            --text-muted: #62687a;
            --accent: #7c8cff;
            --accent-soft: rgba(124, 140, 255, 0.12);
            --accent-border: rgba(124, 140, 255, 0.35);
            --success: #4ade80;
            --success-soft: rgba(74, 222, 128, 0.12);
            --warning: #fbbf24;
            --error: #f87171;
            --error-soft: rgba(248, 113, 113, 0.1);
            --radius: 12px;
        }

        .stApp {
            background:
                radial-gradient(circle at 15% 0%, rgba(124, 140, 255, 0.06), transparent 40%),
                radial-gradient(circle at 85% 15%, rgba(124, 140, 255, 0.04), transparent 35%),
                var(--bg);
        }

        #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
        .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px; }

        section[data-testid="stSidebar"] {
            background: var(--bg-elevated);
            border-right: 1px solid var(--card-border);
        }
        section[data-testid="stSidebar"] * { color: var(--text-secondary); }

        /* ---------- Hero ---------- */
        .hero-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            color: var(--accent);
            background: var(--accent-soft);
            border: 1px solid var(--accent-border);
            padding: 5px 12px;
            border-radius: 999px;
            margin-bottom: 18px;
            text-transform: uppercase;
        }
        .hero-title {
            font-size: 2.6rem;
            font-weight: 800;
            line-height: 1.15;
            color: var(--text-primary);
            letter-spacing: -0.02em;
            margin: 0 0 14px 0;
        }
        .hero-title span { color: var(--accent); }
        .hero-subtitle {
            font-size: 1.02rem;
            color: var(--text-secondary);
            max-width: 640px;
            line-height: 1.6;
            margin-bottom: 0;
        }

        /* ---------- Cards (native st.container(border=True)) ---------- */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--card);
            border: 1px solid var(--card-border) !important;
            border-radius: var(--radius) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            border-radius: var(--radius);
            padding: 10px 8px;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlock"] {
            gap: 0.6rem;
        }

        .section-label {
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 14px;
        }

        /* ---------- Agent pipeline cards ---------- */
        .agent-row { display: flex; gap: 14px; align-items: stretch; }
        .agent-card {
            flex: 1;
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 16px 16px 14px 16px;
            position: relative;
            transition: border-color 0.2s ease;
        }
        .agent-card.state-running {
            border-color: var(--accent-border);
            background: linear-gradient(180deg, var(--accent-soft), var(--card) 70%);
        }
        .agent-card.state-complete { border-color: rgba(74, 222, 128, 0.3); }
        .agent-card.state-error { border-color: rgba(248, 113, 113, 0.35); }

        .agent-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
        .agent-icon {
            width: 26px; height: 26px;
            border-radius: 7px;
            display: flex; align-items: center; justify-content: center;
            font-size: 0.72rem; font-weight: 700;
            background: var(--bg-elevated);
            color: var(--text-secondary);
            border: 1px solid var(--card-border);
        }
        .agent-card.state-running .agent-icon { background: var(--accent); color: #0b0d12; border-color: var(--accent); }
        .agent-card.state-complete .agent-icon { background: var(--success); color: #0b0d12; border-color: var(--success); }

        .agent-name { font-size: 0.86rem; font-weight: 600; color: var(--text-primary); margin: 0 0 3px 0; }
        .agent-desc { font-size: 0.76rem; color: var(--text-muted); line-height: 1.4; margin: 0; }

        .agent-status-pill {
            font-size: 0.62rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
            padding: 2px 8px; border-radius: 999px;
            color: var(--text-muted); background: var(--bg-elevated);
            border: 1px solid var(--card-border);
        }
        .state-running .agent-status-pill { color: var(--accent); border-color: var(--accent-border); background: var(--accent-soft); }
        .state-complete .agent-status-pill { color: var(--success); border-color: rgba(74,222,128,0.3); background: var(--success-soft); }

        .agent-connector {
            display: flex; align-items: center; justify-content: center;
            color: var(--text-muted); font-size: 1rem; width: 18px;
        }

        /* ---------- Inputs & buttons ---------- */
        div[data-testid="stTextInput"] input {
            background: var(--bg-elevated) !important;
            border: 1px solid var(--card-border) !important;
            color: var(--text-primary) !important;
            border-radius: 10px !important;
            padding: 14px 16px !important;
            font-size: 0.95rem !important;
        }
        div[data-testid="stTextInput"] input:focus {
            border-color: var(--accent-border) !important;
            box-shadow: 0 0 0 3px var(--accent-soft) !important;
        }

        .stButton > button, .stDownloadButton > button {
            background: var(--accent) !important;
            color: #0b0d12 !important;
            border: none !important;
            border-radius: 9px !important;
            font-weight: 600 !important;
            padding: 0.55rem 1.1rem !important;
            transition: filter 0.15s ease, transform 0.05s ease;
        }
        .stButton > button:hover, .stDownloadButton > button:hover { filter: brightness(1.08); }
        .stButton > button:active { transform: scale(0.98); }

        button[kind="secondary"] {
            background: var(--card) !important;
            color: var(--text-secondary) !important;
            border: 1px solid var(--card-border) !important;
        }

        /* ---------- Metrics ---------- */
        .metric-card {
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 16px 18px;
            text-align: left;
        }
        .metric-value { font-size: 1.5rem; font-weight: 700; color: var(--text-primary); }
        .metric-label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-top: 2px; }

        /* ---------- Tabs ---------- */
        button[data-baseweb="tab"] {
            color: var(--text-muted) !important;
            font-weight: 500 !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--accent) !important;
        }
        div[data-baseweb="tab-highlight"] { background-color: var(--accent) !important; }
        div[data-baseweb="tab-border"] { background-color: var(--card-border) !important; }

        /* ---------- Report reader (content rendered inside stContainer border=True) ---------- */
        div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] h1,
        div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] h2,
        div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] h3 {
            color: var(--text-primary);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] p,
        div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] li {
            color: #cdd1dc;
            line-height: 1.7;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] code {
            background: var(--bg-elevated);
            padding: 2px 6px;
            border-radius: 5px;
            font-family: 'JetBrains Mono', monospace;
        }

        .report-footer { color: var(--text-muted); font-size: 0.78rem; margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--card-border); }

        /* ---------- Empty state ---------- */
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            border: 1px dashed var(--card-border);
            border-radius: var(--radius);
            background: var(--card);
        }
        .empty-state .hero-badge { margin-bottom: 16px; }
        .empty-title { font-size: 1.15rem; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
        .empty-desc { color: var(--text-muted); font-size: 0.88rem; max-width: 440px; margin: 0 auto; line-height: 1.6; }

        hr { border-color: var(--card-border) !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        st.markdown(
            "<div style='font-weight:700;color:#e9ebf1;font-size:1rem;"
            "letter-spacing:-0.01em;margin-bottom:2px;'>Research Intelligence</div>"
            "<div style='color:#62687a;font-size:0.78rem;margin-bottom:22px;'>Multi-agent AI system</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div class='section-label'>Agents</div>", unsafe_allow_html=True)
        for stage in STAGE_ORDER:
            info = STAGE_INFO[stage]
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:9px;"
                f"font-size:0.83rem;color:#cdd1dc;'>"
                f"<span style='color:#7c8cff;'>&#9679;</span> {info['label']}</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        st.markdown("<div class='section-label'>System</div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='font-size:0.83rem;color:#9aa1b1;line-height:1.6;'>"
            "Powered by the project's research pipeline "
            "(<code>pipeline.run_research_pipeline</code>).</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        st.markdown("<div class='section-label'>About</div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='font-size:0.83rem;color:#9aa1b1;line-height:1.6;'>"
            "A multi-agent workflow that searches, reads, writes, and critiques "
            "research on a given topic, with each stage handled by a dedicated agent.</div>",
            unsafe_allow_html=True,
        )


def render_hero():
    st.markdown(
        """
        <div class="hero-badge">&#10022; Multi-Agent AI Research</div>
        <div class="hero-title">Research Intelligence,<br>Powered by AI <span>Agents</span>.</div>
        <div class="hero-subtitle">
            Specialized agents search, read, synthesize, and critique — turning a topic
            into a structured, reviewed research report.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)


def agent_card_html(stage: str, state: str) -> str:
    info = STAGE_INFO[stage]
    state_label = {
        "waiting": "Waiting",
        "running": "Running",
        "complete": "Complete",
        "error": "Error",
    }.get(state, "Waiting")
    icon = "&#10003;" if state == "complete" else info["icon"]
    return f"""
    <div class="agent-card state-{state}">
        <div class="agent-top">
            <span class="agent-icon">{icon}</span>
            <span class="agent-status-pill">{state_label}</span>
        </div>
        <div class="agent-name">{info['label']}</div>
        <div class="agent-desc">{info['desc']}</div>
    </div>
    """


def render_pipeline_panel(statuses: dict, placeholders: dict = None):
    """Renders the 4-stage agent pipeline. If placeholders is given, writes
    into those st.empty() slots so it can be updated live during execution."""
    cols = st.columns([1, 0.06, 1, 0.06, 1, 0.06, 1])
    slots = {}
    for i, stage in enumerate(STAGE_ORDER):
        col_idx = i * 2
        with cols[col_idx]:
            ph = st.empty()
            ph.markdown(agent_card_html(stage, statuses[stage]), unsafe_allow_html=True)
            slots[stage] = ph
        if col_idx + 1 < len(cols) - 1:
            with cols[col_idx + 1]:
                st.markdown(
                    "<div class='agent-connector'>&#8594;</div>", unsafe_allow_html=True
                )
    return slots


def render_input_area():
    card = st.container(border=True)
    with card:
        st.markdown("<div class='section-label'>Research Topic</div>", unsafe_allow_html=True)

        col_input, col_btn = st.columns([5, 1.1])
        with col_input:
            topic = st.text_input(
                "Research topic",
                key="topic_input",
                placeholder="e.g. Impact of Generative AI on Software Engineering",
                label_visibility="collapsed",
            )
        with col_btn:
            start_clicked = st.button(
                "Start Research →", type="primary", use_container_width=True
            )

        st.markdown(
            "<div style='font-size:0.76rem;color:#62687a;margin-top:10px;'>Try:</div>",
            unsafe_allow_html=True,
        )
        chip_cols = st.columns(len(EXAMPLE_TOPICS))
        for i, example in enumerate(EXAMPLE_TOPICS):
            with chip_cols[i]:
                if st.button(example, key=f"example_{i}", use_container_width=True):
                    st.session_state.topic_input = example
                    st.rerun()

    return topic, start_clicked


def render_empty_state():
    st.markdown(
        """
        <div class="empty-state">
            <div class="hero-badge">&#10022; Ready to Research</div>
            <div class="empty-title">Enter a topic above to begin</div>
            <div class="empty-desc">
                The search, reader, writer, and critic agents will find, analyze,
                write, and review the research in sequence.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_error_state():
    st.markdown(
        """
        <div class="card" style="border-color: rgba(248,113,113,0.35); background: rgba(248,113,113,0.06);">
            <div style="color:#f87171; font-weight:600; margin-bottom:6px;">Research could not be completed</div>
            <div style="color:#9aa1b1; font-size:0.88rem; line-height:1.6;">
                Please verify your API configuration, check your network connection, or try again
                with a different topic. Technical details have been logged for the developer.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(result: dict):
    report_text = result.get("report") or ""
    word_count = len(report_text.split()) if report_text else 0
    has_feedback = bool(result.get("feedback"))
    has_sources = bool(result.get("search_results") or result.get("scraped_content"))

    metrics = [
        ("4", "Agents in pipeline"),
        (f"{word_count}", "Words in report"),
        ("Yes" if has_sources else "No", "Sources gathered"),
        ("Yes" if has_feedback else "No", "Critic reviewed"),
    ]
    cols = st.columns(4)
    for col, (value, label) in zip(cols, metrics):
        with col:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-value">{value}</div>
                    <div class="metric-label">{label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_copy_button(text: str, key: str):
    escaped = (
        text.replace("\\", "\\\\").replace("`", "\\`").replace("</", "<\\/")
    )
    components.html(
        f"""
        <button id="copy-btn-{key}" style="
            background:#151922;color:#9aa1b1;border:1px solid #232733;
            border-radius:9px;padding:8px 16px;font-family:Inter,sans-serif;
            font-size:0.82rem;font-weight:600;cursor:pointer;">
            Copy report
        </button>
        <script>
        const btn = document.getElementById("copy-btn-{key}");
        btn.addEventListener("click", () => {{
            const text = `{escaped}`;
            navigator.clipboard.writeText(text).then(() => {{
                btn.innerText = "Copied";
                setTimeout(() => btn.innerText = "Copy report", 1500);
            }});
        }});
        </script>
        """,
        height=45,
    )


def render_report(report: str, topic: str):
    shell = st.container(border=True)
    with shell:
        st.markdown(
            f"<div style='color:#62687a;font-size:0.76rem;text-transform:uppercase;"
            f"letter-spacing:0.08em;margin-bottom:4px;'>Topic</div>"
            f"<div style='color:#e9ebf1;font-size:1.1rem;font-weight:600;margin-bottom:22px;'>{topic}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(report or "_No report was generated._")
        st.markdown(
            "<div class='report-footer'>Research generated by the multi-agent research pipeline "
            "(Search → Reader → Writer → Critic).</div>",
            unsafe_allow_html=True,
        )


def render_critic(feedback: str):
    shell = st.container(border=True)
    with shell:
        st.markdown(
            "<div style='color:#62687a;font-size:0.76rem;text-transform:uppercase;"
            "letter-spacing:0.08em;margin-bottom:14px;'>Critic Review</div>",
            unsafe_allow_html=True,
        )
        st.markdown(feedback or "_No critic feedback was generated._")


def render_raw_section(label: str, content: str):
    shell = st.container(border=True)
    with shell:
        st.markdown(
            f"<div style='color:#62687a;font-size:0.76rem;text-transform:uppercase;"
            f"letter-spacing:0.08em;margin-bottom:14px;'>{label}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(content or f"_No {label.lower()} available._")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
inject_css()
render_sidebar()
render_hero()

topic, start_clicked = render_input_area()

st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)

pipeline_container = st.container()

if start_clicked:
    if not topic or not topic.strip():
        st.error("Please enter a research topic before starting.")
    else:
        st.session_state.error = None
        st.session_state.result = None
        clean_topic = topic.strip()
        st.session_state.is_running = True

        statuses = {s: "waiting" for s in STAGE_ORDER}

        with pipeline_container:
            st.markdown("<div class='section-label'>Research Pipeline</div>", unsafe_allow_html=True)
            slots = render_pipeline_panel(statuses)

        def on_stage(stage: str):
            if stage not in STAGE_ORDER:
                return 
            idx = STAGE_ORDER.index(stage)
            for i, s in enumerate(STAGE_ORDER):
                if i < idx:
                    statuses[s] = "complete"
                elif i == idx:
                    statuses[s] = "running"
            for s, ph in slots.items():
                ph.markdown(agent_card_html(s, statuses[s]), unsafe_allow_html=True)

        try:
            result = run_research_pipeline(clean_topic, status_callback=on_stage)
            for s in STAGE_ORDER:
                statuses[s] = "complete"
            for s, ph in slots.items():
                ph.markdown(agent_card_html(s, statuses[s]), unsafe_allow_html=True)

            st.session_state.result = result
            st.session_state.topic = clean_topic
        except Exception as e:
            print(f"[Pipeline Error] {type(e).__name__}: {e}")
            for s in STAGE_ORDER:
                if statuses[s] == "running":
                    statuses[s] = "error"
            for s, ph in slots.items():
                ph.markdown(agent_card_html(s, statuses[s]), unsafe_allow_html=True)
            st.session_state.error = str(e)
        finally:
            st.session_state.is_running = False

# ---------------------------------------------------------------------------
# Idle / architecture preview (only when nothing has run yet and not mid-run)
# ---------------------------------------------------------------------------
if not start_clicked and not st.session_state.result and not st.session_state.error:
    with pipeline_container:
        st.markdown("<div class='section-label'>Research Pipeline</div>", unsafe_allow_html=True)
        render_pipeline_panel({s: "waiting" for s in STAGE_ORDER})
    st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
    render_empty_state()

# ---------------------------------------------------------------------------
# Error state
# ---------------------------------------------------------------------------
if st.session_state.error:
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    render_error_state()

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
if st.session_state.result:
    result = st.session_state.result
    st.markdown("<div style='height:34px;'></div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='color:#4ade80;font-size:0.78rem;font-weight:700;letter-spacing:0.06em;"
        f"text-transform:uppercase;margin-bottom:4px;'>&#10003; Research Complete</div>"
        f"<div style='color:#e9ebf1;font-size:1.3rem;font-weight:700;margin-bottom:20px;'>{st.session_state.topic}</div>",
        unsafe_allow_html=True,
    )

    render_metrics(result)
    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)

    tab_report, tab_sources, tab_reader, tab_critic = st.tabs(
        ["Final Report", "Sources", "Reader Notes", "Critic"]
    )

    with tab_report:
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        report_text = result.get("report") or ""

        action_cols = st.columns([1, 1, 6])
        with action_cols[0]:
            st.download_button(
                "Download .md",
                data=report_text,
                file_name=f"{st.session_state.topic[:40].strip().replace(' ', '_') or 'report'}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with action_cols[1]:
            st.download_button(
                "Download .txt",
                data=report_text,
                file_name=f"{st.session_state.topic[:40].strip().replace(' ', '_') or 'report'}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        if report_text:
            render_copy_button(report_text, key="report")

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        render_report(report_text, st.session_state.topic)

    with tab_sources:
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        render_raw_section("Search Results", result.get("search_results"))

    with tab_reader:
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        render_raw_section("Scraped Content", result.get("scraped_content"))

    with tab_critic:
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        render_critic(result.get("feedback"))