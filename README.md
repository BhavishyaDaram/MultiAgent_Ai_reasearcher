# AI Multi-Agent Research Assistant

## Project Overview

**AI Multi-Agent Research Assistant** is a multi-agent research system that takes
a topic from the user and automatically searches the web, reads the most
relevant source in depth, drafts a structured research report, and critiques
that report — all through a clean Streamlit web interface.

The underlying agent pipeline was already functional as a command-line tool.
This project adds a professional Streamlit UI on top of the existing
multi-agent architecture without changing how the agents work internally.

## Key Features

- **Multi-agent research pipeline** — four distinct stages (Search → Read →
  Write → Critic), each handled by its own agent/chain.
- **Web search** — a search agent backed by the Tavily search API finds
  recent, relevant sources for the topic.
- **Resource reading / scraping** — a reader agent picks the most relevant
  result and scrapes its page content for deeper context.
- **AI-generated report** — a writer chain produces a structured report
  (Introduction, Key Findings, Conclusion, Sources).
- **Critic / reviewer stage** — a critic chain scores the report and lists
  strengths and areas to improve.
- **Streamlit interface** — topic input, a live "Start Research" button, and
  real-time stage-by-stage progress.
- **Structured, tabbed output** — Final Report, Search Results, Scraped
  Content, and Critic Feedback, each in its own tab.

## Architecture

```text
User
 ↓
Streamlit UI (app.py)
 ↓
Research Pipeline (pipeline.py)
 ↓
Search Agent   → finds candidate sources for the topic
 ↓
Reader Agent   → scrapes the most relevant source for deeper content
 ↓
Writer         → drafts a structured report from search + scraped content
 ↓
Critic         → reviews the report and gives a score, strengths, and
                  areas to improve
 ↓
Final Report (shown in the UI)
```

- **`app.py`** — the Streamlit UI. Collects the topic, triggers the
  pipeline, shows live stage progress, and renders the results.
- **`pipeline.py`** — orchestrates the four pipeline stages in order and
  returns the combined state. Unchanged in behavior; it can still be run
  directly from the command line.
- **`agents.py`** — defines the LLM, the search agent, the reader agent, the
  writer chain, and the critic chain.
- **`tools.py`** — defines the two tools used by the agents: `web_search`
  (Tavily) and `scrape_url` (requests + BeautifulSoup).

## Technologies Used

- Python
- Streamlit
- LangChain (`langchain`, `langchain-core`, `langchain-community`)
- Google Gemini (`langchain-google-genai`, model: `gemini-flash-lite-latest`)
- Tavily (web search)
- BeautifulSoup + Requests (web scraping)
- python-dotenv (environment variable loading)

## Project Structure

```text
project/
│
├── app.py
├── agents.py
├── pipeline.py
├── tools.py
├── requirements.txt
├── README.md
└── .env
```

## Installation

```bash
git clone <repository-url>
cd <project-folder>
```

Create and activate a virtual environment.

**Windows:**

```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root:

```text
GOOGLE_API_KEY=your_google_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```

- `TAVILY_API_KEY` is read explicitly in `tools.py` and is required for the
  search agent's `web_search` tool.
- `GOOGLE_API_KEY` is the standard environment variable that
  `langchain-google-genai`'s `ChatGoogleGenerativeAI` looks for to
  authenticate with the Gemini API.

## Running the Application

Start the Streamlit app:

```bash
streamlit run app.py
```

This opens the app in your browser (usually at `http://localhost:8501`).

The original CLI pipeline still works exactly as before and can be run
directly, independent of the Streamlit UI:

```bash
python pipeline.py
```

## How It Works

1. The user enters a research topic and clicks **Start Research**.
2. The **Search Agent** uses the `web_search` tool to find recent, reliable
   sources on the topic.
3. The **Reader Agent** picks the most relevant result from the search output
   and scrapes it with the `scrape_url` tool for deeper content.
4. The **Writer** combines the search results and scraped content into a
   structured report (Introduction, Key Findings, Conclusion, Sources).
5. The **Critic** reviews the report and returns a score, strengths, and
   areas to improve.
6. The Streamlit UI displays the final report as the primary tab, with the
   raw search results, scraped content, and critic feedback available in
   their own tabs.

## Agent Responsibilities

| Component | Responsibility |
|---|---|
| Search Agent | Uses the `web_search` tool (Tavily) to find recent, relevant sources for the given topic. |
| Reader Agent | Uses the `scrape_url` tool to read and extract clean text content from the most relevant source. |
| Writer Chain | Synthesizes the search results and scraped content into a structured, professional report. |
| Critic Chain | Reviews the report strictly, giving a score out of 10, strengths, areas to improve, and a one-line verdict. |

## Example Usage

Try entering a topic such as:

```text
Impact of Generative AI on Software Engineering
```

The exact content of the report and critique will vary by run, since both
depend on live web search results and the LLM's response.

## Screenshots

Add screenshots of the Streamlit application here.

## Future Improvements

The following are potential future improvements and are **not** currently
implemented:

- Comparing and synthesizing multiple sources instead of a single scraped
  page.
- Automatic citation extraction and inline citations in the report.
- Exporting the final report as a PDF.
- Persisted research history across sessions.
- Source credibility scoring.
- More sophisticated multi-agent orchestration (e.g. parallel search +
  reading of several sources).
- Streaming agent output token-by-token instead of per-stage updates.

## Disclaimer / Limitations

This application uses AI agents and live web search to generate research
reports automatically. The output may be incomplete, out of date, or
inaccurate, and should be verified against original sources before being
relied upon for important decisions.
