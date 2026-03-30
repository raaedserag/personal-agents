import json
import os
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path(__file__).parent
SUMMARIES_DIR = MEMORY_DIR / "summaries"
LOGS_DIR = MEMORY_DIR / "logs"

SUMMARIES_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)


def save_query_log(query, response):
    log_file = LOGS_DIR / "queries.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "query": query[:500],
        "response": response[:1000],
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def save_daily_summary(summary_text):
    today = datetime.now().strftime("%Y-%m-%d")
    summary_file = SUMMARIES_DIR / f"{today}.json"
    data = {
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "summary": summary_text,
    }
    with open(summary_file, "w") as f:
        json.dump(data, f, indent=2)


def load_recent_context(days=3):
    lines = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        summary_file = SUMMARIES_DIR / f"{date}.json"
        if summary_file.exists():
            with open(summary_file) as f:
                data = json.load(f)
                lines.append(f"[{data['date']}] {data['summary']}")

    # Also grab last 5 query logs for immediate context
    log_file = LOGS_DIR / "queries.jsonl"
    if log_file.exists():
        with open(log_file) as f:
            all_lines = f.readlines()
        recent = all_lines[-5:]
        for line in recent:
            entry = json.loads(line)
            lines.append(f"[{entry['timestamp'][:16]}] Q: {entry['query'][:100]}")

    return "\n".join(lines) if lines else ""
