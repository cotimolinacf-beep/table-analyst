"""
SQLite utilities: load CSV/Excel files and inspect schema.
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd

DB_DIR = Path("databases")
DB_PATH = DB_DIR / "data.db"


def load_file_to_sqlite(file_path: str, table_name: str = "data") -> dict:
    """Load a CSV or Excel file into SQLite. Returns metadata dict."""
    DB_DIR.mkdir(exist_ok=True)
    path = Path(file_path)
    suffix = path.suffix.lower()

    try:
        if suffix == ".csv":
            df = pd.read_csv(file_path, low_memory=False)
        elif suffix in (".xls", ".xlsx"):
            df = pd.read_excel(file_path)
        else:
            return {"success": False, "error": f"Unsupported file type: {suffix}"}

        # Sanitize column names
        df.columns = [str(c).strip() for c in df.columns]

        conn = sqlite3.connect(DB_PATH)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()

        return {
            "success": True,
            "table_name": table_name,
            "columns": list(df.columns),
            "row_count": len(df),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_schema_info() -> list:
    """Return schema info for all tables in the database."""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()

    schema = []
    for (table_name,) in tables:
        row_count = cursor.execute(
            f'SELECT COUNT(*) FROM "{table_name}"'
        ).fetchone()[0]

        cols_info = cursor.execute(
            f'PRAGMA table_info("{table_name}")'
        ).fetchall()

        columns = []
        for col in cols_info:
            col_name, col_type = col[1], col[2]
            samples = cursor.execute(
                f'SELECT DISTINCT "{col_name}" FROM "{table_name}" '
                f'WHERE "{col_name}" IS NOT NULL LIMIT 3'
            ).fetchall()
            columns.append({
                "name": col_name,
                "type": col_type,
                "samples": [str(r[0]) for r in samples],
            })

        schema.append({
            "table_name": table_name,
            "row_count": row_count,
            "columns": columns,
        })

    conn.close()
    return schema


def format_schema_for_llm() -> str:
    """Return a human-readable schema string for the LLM context."""
    schema = get_schema_info()
    if not schema:
        return "No tables found in the database."

    lines = []
    for table in schema:
        lines.append(f"Table: {table['table_name']} ({table['row_count']:,} rows)")
        lines.append("Columns:")
        for col in table["columns"]:
            samples = ", ".join(repr(s) for s in col["samples"])
            lines.append(f"  - {col['name']} ({col['type']}) | samples: {samples}")
        lines.append("")

    return "\n".join(lines)


def run_query(query: str) -> dict:
    """Execute a SQL SELECT query and return results."""
    if not DB_PATH.exists():
        return {"success": False, "error": "No database loaded."}

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)

        if cursor.description:
            columns = [d[0] for d in cursor.description]
            rows = [list(r) for r in cursor.fetchall()]
            conn.close()
            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }

        conn.commit()
        conn.close()
        return {"success": True, "message": "OK"}
    except Exception as e:
        return {"success": False, "error": str(e)}
