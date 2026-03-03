"""
LangGraph analysis agent: runs SQL queries autonomously and produces a
markdown report from the user's analysis prompt.
"""
from __future__ import annotations

import json
import os
from typing import Annotated

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from db import format_schema_for_llm, load_file_to_sqlite, run_query
from prompts import ANALYSIS_SYSTEM_TEMPLATE

load_dotenv()


# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------
@tool
def execute_sql(query: str) -> str:
    """Execute a read-only SQLite SELECT query and return results as JSON.

    Args:
        query: a SQLite SELECT statement.
    """
    upper = query.strip().upper()
    if any(
        upper.startswith(kw)
        for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE")
    ):
        return json.dumps({"error": "Only SELECT queries are allowed."})

    result = run_query(query)
    if result["success"]:
        if "columns" in result:
            return json.dumps({
                "columns": result["columns"],
                "rows": result["rows"][:100],
                "total_rows": result["row_count"],
            })
        return json.dumps({"message": result.get("message", "OK")})
    return json.dumps({"error": result["error"]})


TOOLS = [execute_sql]


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
def _get_api_key() -> str:
    """Read API key from .env (local) or Streamlit secrets (cloud)."""
    key = os.getenv("GOOGLE_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        key = st.secrets.get("GOOGLE_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    raise EnvironmentError(
        "GOOGLE_API_KEY not found. Set it in .env (local) or "
        "Streamlit Cloud secrets (dashboard)."
    )


def _get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        temperature=0,
        google_api_key=_get_api_key(),
    )


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------
def build_analysis_graph(schema: str):
    """Build a LangGraph that loops agent ↔ SQL tools until the report is ready."""
    system_prompt = SystemMessage(
        content=ANALYSIS_SYSTEM_TEMPLATE.format(schema=schema)
    )

    def analysis_agent(state: AgentState) -> dict:
        llm = _get_llm().bind_tools(TOOLS)
        response = llm.invoke([system_prompt] + state["messages"])
        return {"messages": [response]}

    def router(state: AgentState) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    tool_node = ToolNode(TOOLS)

    g = StateGraph(AgentState)
    g.add_node("agent", analysis_agent)
    g.add_node("tools", tool_node)

    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", router)
    g.add_edge("tools", "agent")  # loop back after each tool call

    return g.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
class AnalysisSystem:
    """Load a data file and run analysis prompts against it."""

    def __init__(self):
        self.schema: str = ""

    def load_file(self, file_path: str) -> str:
        """Load CSV/Excel into SQLite. Returns the schema string."""
        result = load_file_to_sqlite(file_path)
        if not result["success"]:
            raise ValueError(result["error"])
        self.schema = format_schema_for_llm()
        return self.schema

    def analyze(self, prompt: str) -> str:
        """Run the analysis agent and return the markdown report."""
        if not self.schema:
            raise ValueError("No data loaded. Please upload a file first.")

        graph = build_analysis_graph(self.schema)
        result = graph.invoke({"messages": [HumanMessage(content=prompt)]})

        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                return msg.content

        return "No analysis could be generated."
