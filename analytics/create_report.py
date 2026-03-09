import os
import psycopg
from datetime import datetime, UTC
from jinja2 import Template
from dotenv import load_dotenv

load_dotenv()

# DB connection parameters
USER = os.environ.get("POSTGRES_USER", "postgres")
PW = os.environ.get("POSTGRES_PASSWORD", "postgres")
ADDRESS = os.environ.get("POSTGRES_ADDRESS", "127.0.0.1")
PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
DB_NAME = os.environ.get("POSTGRES_DB", "postgres")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_DIR = os.path.join(BASE_DIR, "sql")
TPL_DIR = os.path.join(BASE_DIR, "templates")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# Create reports directory if it doesn't exist
os.makedirs(REPORTS_DIR, exist_ok=True)


def load_sql_files() -> dict[str, str]:
    """
    Load all SQL files from /sql directory.

    Returns:
        dict[str, str]: SQL query name -> SQL query content mapping
    """
    queries = {}
    for filename in os.listdir(SQL_DIR):
        if filename.endswith(".sql"):
            key = filename.replace(".sql", "")
            with open(os.path.join(SQL_DIR, filename), "r") as f:
                queries[key] = f.read()
    return queries


def run_queries(queries: dict[str, str]) -> dict[str, list[dict]]:
    """
    Execute SQL queries using psycopg3 with clean defaults.

    Args:
        queries: dict[str, str] - SQL query name -> SQL query content mapping

    Returns:
        dict[str, list[dict]]: Query name -> list of result rows (as dicts) mapping
    """
    results = {}

    with psycopg.connect(
        dbname=DB_NAME,
        user=USER,
        password=PW,
        host=ADDRESS,
        port=PORT,
    ) as conn:
        with conn.cursor() as cur:
            for name, sql in queries.items():
                cur.execute(sql)
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                results[name] = [dict(zip(columns, row)) for row in rows]

    return results


def aggregate_statistics(data: dict[str, list[dict]]) -> dict[str, int]:
    """
    Calculate summary statistics from query results.

    Args:
        data: dict[str, list[dict]] - Query results mapping

    Returns:
        dict[str, int]: Statistics key -> value mapping
    """
    stats = {}

    # Total records
    count_records = data.get("count_records_per_endpoint", [])
    stats["total_records"] = sum(row.get("record_count", 0) for row in count_records)

    # Total harvest events
    summary = data.get("summary", [])
    stats["total_events"] = sum(row.get("total_harvest_events", 0) for row in summary)

    return stats


def render_markdown(data: dict[str, list[dict]]) -> str:
    """
    Render Markdown report using Jinja2 template.

    Args:
        data: dict[str, list[dict]] - Query results mapping

    Returns:
        str: Rendered Markdown report content
    """
    template_path = os.path.join(TPL_DIR, "report.md.jinja")

    # Calculate aggregated statistics
    stats = aggregate_statistics(data)

    with open(template_path) as f:
        template = Template(f.read())

    return template.render(
        generated_at=datetime.now(UTC).isoformat(),
        database_name=DB_NAME,
        **data,
        **stats
    )


def save_report(content: str) -> None:
    """
    Save the Markdown report to a timestamped file in reports/ directory.

    Args:
        content: str - Rendered Markdown report content

    Returns:
        None
    """
    filename = f"report_{datetime.now(UTC).strftime('%Y-%m-%d_%H-%M-%S')}.md"
    output_path = os.path.join(REPORTS_DIR, filename)

    with open(output_path, "w") as f:
        f.write(content)

    print(f"✓ Report saved to {output_path}")


if __name__ == "__main__":
    sql_queries = load_sql_files()
    query_results = run_queries(sql_queries)
    markdown = render_markdown(query_results)
    save_report(markdown)
