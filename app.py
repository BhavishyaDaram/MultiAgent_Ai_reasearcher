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
