import os
import hmac
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from skills import TOOL_REGISTRY
from skills.jira_fetcher import get_my_open_tickets, get_ticket_details

load_dotenv()

AGENT_API_KEY = os.getenv("AGENT_API_KEY", "")

app = FastAPI(title="Zeal Jira Agent API", version="1.0.0")


def _verify_api_key(x_api_key: str = Header(None)):
    if not AGENT_API_KEY:
        raise HTTPException(status_code=500, detail="AGENT_API_KEY not configured on server.")
    if x_api_key is None or not hmac.compare_digest(x_api_key, AGENT_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


class QueryRequest(BaseModel):
    query: str
    project_key: str = ""


class QueryResponse(BaseModel):
    status: str
    data: str


@app.get("/health")
def health():
    return {"status": "ok", "agent": "zeal-jira-worker", "version": "1.0.0"}


@app.get("/tickets/mine")
def my_tickets(x_api_key: str = Header(None)):
    _verify_api_key(x_api_key)
    result = get_my_open_tickets()
    return QueryResponse(status="ok", data=result)


@app.get("/tickets/{issue_key}")
def ticket_details(issue_key: str, x_api_key: str = Header(None)):
    _verify_api_key(x_api_key)
    result = get_ticket_details(issue_key)
    return QueryResponse(status="ok", data=result)


@app.post("/query")
def query_agent(req: QueryRequest, x_api_key: str = Header(None)):
    _verify_api_key(x_api_key)
    query = req.query.lower()

    # Simple routing for direct API queries from other agents
    if "my open tickets" in query or "my tickets" in query:
        return QueryResponse(status="ok", data=get_my_open_tickets())

    if "blocked" in query:
        from skills.jira_fetcher import get_blocked_tickets
        return QueryResponse(status="ok", data=get_blocked_tickets(req.project_key))

    if "search" in query or "find" in query:
        from skills.jira_fetcher import search_tickets
        # Strip the command words to get the actual search query
        search_text = query.replace("search", "").replace("find", "").strip()
        return QueryResponse(status="ok", data=search_tickets(search_text, req.project_key))

    # For complex queries, we'd integrate the full ReAct loop here in the future
    return QueryResponse(
        status="unsupported",
        data="Complex queries require the full orchestrator. Use the terminal CLI for now, or use specific endpoints: /tickets/mine, /tickets/{key}",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
