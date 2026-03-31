"""
AGENT_NAME API — FastAPI endpoints.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Depends

sys.path.insert(0, "/app")
from shared.auth import verify_api_key
from shared.models import QueryResponse

load_dotenv()

PROFILE_ID = os.getenv("PROFILE_ID", "unknown")
AGENT_ID = f"AGENT_NAME-{PROFILE_ID}"

app = FastAPI(title=f"Nerve Center AGENT_NAME ({PROFILE_ID})", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "agent": AGENT_ID, "profile": PROFILE_ID, "version": "1.0.0"}


@app.post("/query")
def query_agent(query: str, _key: str = Depends(verify_api_key)):
    return QueryResponse(status="unsupported", agent_id=AGENT_ID, error="Not yet implemented.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
