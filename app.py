"""
Streamlit UI for Table Analyst.
Usage: streamlit run app.py
"""
import os
import tempfile
from pathlib import Path

import streamlit as st

from analyzer import AnalysisSystem

st.set_page_config(page_title="Table Analyst", layout="wide")

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
if "system" not in st.session_state:
    st.session_state.system = AnalysisSystem()
if "schema" not in st.session_state:
    st.session_state.schema = ""
if "filename" not in st.session_state:
    st.session_state.filename = ""
if "report" not in st.session_state:
    st.session_state.report = ""

system: AnalysisSystem = st.session_state.system

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Table Analyst")
st.caption("Upload a CSV or Excel file, describe what you want to analyze, and get a data-driven report.")

if st.session_state.schema:
    if st.button("↩ Start over", type="secondary"):
        st.session_state.schema = ""
        st.session_state.filename = ""
        st.session_state.report = ""
        st.session_state.system = AnalysisSystem()
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Step 1 — Upload
# ---------------------------------------------------------------------------
st.subheader("1 · Upload your data")

uploaded = st.file_uploader(
    "CSV or Excel file",
    type=["csv", "xls", "xlsx"],
    label_visibility="collapsed",
)

if uploaded and uploaded.name != st.session_state.filename:
    suffix = Path(uploaded.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    with st.spinner("Loading file into database..."):
        try:
            schema = system.load_file(tmp_path)
            st.session_state.schema = schema
            st.session_state.filename = uploaded.name
            st.session_state.report = ""
        except Exception as e:
            st.error(f"Error loading file: {e}")
        finally:
            os.unlink(tmp_path)

if st.session_state.schema:
    with st.expander(f"Schema — {st.session_state.filename}", expanded=False):
        st.code(st.session_state.schema, language=None)

    st.divider()

    # -----------------------------------------------------------------------
    # Step 2 — Prompt
    # -----------------------------------------------------------------------
    st.subheader("2 · What do you want to analyze?")

    TEMPLATES = {
        "— choose a template or write your own —": "",
        "Executive summary": (
            "Generate a comprehensive executive summary of this dataset. "
            "Cover key statistics, distributions across main categories, "
            "and the most notable patterns or outliers."
        ),
        "Top performers": (
            "Identify and rank the top performers in this dataset. "
            "Explain what distinguishes them from the rest with concrete numbers."
        ),
        "Trends over time": (
            "Analyze how the key metrics evolve over time in this dataset. "
            "Identify growth, decline, and any seasonal or cyclical patterns."
        ),
        "Distribution overview": (
            "Provide a full distribution analysis of the main categorical "
            "and numerical columns. Include value counts, percentages, and "
            "any imbalances worth noting."
        ),
    }

    selected = st.selectbox("Quick templates", options=list(TEMPLATES.keys()))
    default_prompt = TEMPLATES[selected]

    prompt = st.text_area(
        "Analysis prompt",
        value=default_prompt,
        height=130,
        placeholder=(
            "e.g. Analyze sales performance by region and identify "
            "top-performing areas with trends over time."
        ),
    )

    if st.button("Generate Report", type="primary", disabled=not prompt.strip()):
        with st.spinner("Analyzing data — the agent is running SQL queries..."):
            try:
                report = system.analyze(prompt)
                st.session_state.report = report
            except Exception as e:
                st.error(f"Analysis error: {e}")

    # -----------------------------------------------------------------------
    # Step 3 — Report
    # -----------------------------------------------------------------------
    if st.session_state.report:
        st.divider()
        st.subheader("3 · Analysis Report")

        st.download_button(
            label="Download as Markdown",
            data=st.session_state.report.encode("utf-8"),
            file_name="report.md",
            mime="text/markdown",
        )

        st.markdown(st.session_state.report)
