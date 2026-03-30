import os
import re
import json
import requests
from dotenv import load_dotenv
from pathlib import Path
from skills import TOOL_REGISTRY, WRITE_TOOLS
from memory.memory_manager import save_query_log, load_recent_context

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = "llama3.2"
MAX_TOOL_CALLS_PER_TURN = 3

AGENT_DIR = Path(__file__).parent
SOUL = (AGENT_DIR / "SOUL.md").read_text()
DUTIES = (AGENT_DIR / "DUTIES.md").read_text()

TOOL_DESCRIPTIONS = """Available tools (use exactly this format to call them):

READ tools (no confirmation needed):
- <TOOL:get_my_open_tickets(max_results="10")> — Fetch your open tickets. max_results is optional.
- <TOOL:get_team_open_tickets(project_key="ATH", max_results="20")> — Fetch open tickets for a project. project_key required.
- <TOOL:get_ticket_details(issue_key="ATH-123")> — Get full details + comments for a ticket.
- <TOOL:search_tickets(query="payment bug", project_key="ATH")> — Search tickets by text. project_key is optional.
- <TOOL:get_blocked_tickets(project_key="ATH")> — List blocked tickets. project_key is optional.

WRITE tools (will ask user for confirmation before executing):
- <TOOL:transition_ticket(issue_key="ATH-123", target_status="In Progress")> — Move ticket to a new status.
- <TOOL:add_comment(issue_key="ATH-123", comment_body="Working on this now.")> — Add a comment.
- <TOOL:assign_ticket(issue_key="ATH-123", assignee_email="user@getzeal.io")> — Assign ticket to someone.
- <TOOL:create_ticket(project_key="ATH", summary="Fix login bug", description="Details here", issue_type="Task")> — Create a new ticket.

Rules:
- Call ONE tool at a time. Wait for the result before deciding next steps.
- Never fabricate ticket data. Always use tools to verify.
- For write operations, the user will be asked to confirm before execution.
"""

SYSTEM_PROMPT = f"{SOUL}\n\n---\n\n{DUTIES}\n\n---\n\n{TOOL_DESCRIPTIONS}"

TOOL_CALL_PATTERN = re.compile(r"<TOOL:(\w+)\(([^)]*)\)>")


def parse_tool_call(text):
    match = TOOL_CALL_PATTERN.search(text)
    if not match:
        return None, None
    func_name = match.group(1)
    args_str = match.group(2)
    kwargs = {}
    if args_str.strip():
        for pair in re.findall(r'(\w+)\s*=\s*"([^"]*)"', args_str):
            kwargs[pair[0]] = pair[1]
    return func_name, kwargs


def execute_tool(func_name, kwargs):
    if func_name not in TOOL_REGISTRY:
        return f"Unknown tool: {func_name}"
    func = TOOL_REGISTRY[func_name]
    try:
        return func(**kwargs)
    except TypeError as e:
        return f"Tool call error: {e}"


def confirm_write(func_name, kwargs):
    print(f"\n⚠  Write operation requested: {func_name}")
    print(f"   Arguments: {kwargs}")
    answer = input("   Execute? [y/N]: ").strip().lower()
    return answer == "y"


def chat_with_ollama(messages):
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": MODEL, "messages": messages, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to Ollama. Is it running on localhost:11434?"
    except requests.exceptions.Timeout:
        return "Error: Ollama request timed out (120s). Try a simpler query."
    except Exception as e:
        return f"Error talking to Ollama: {e}"


def stream_chat_with_ollama(messages):
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": MODEL, "messages": messages, "stream": True},
            timeout=120,
            stream=True,
        )
        resp.raise_for_status()
        full_response = []
        for line in resp.iter_lines():
            if line:
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    print(token, end="", flush=True)
                    full_response.append(token)
                if chunk.get("done"):
                    break
        print()
        return "".join(full_response)
    except requests.exceptions.ConnectionError:
        msg = "Error: Cannot connect to Ollama. Is it running on localhost:11434?"
        print(msg)
        return msg
    except Exception as e:
        msg = f"Error talking to Ollama: {e}"
        print(msg)
        return msg


def run_react_turn(user_input, conversation_history):
    conversation_history.append({"role": "user", "content": user_input})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    tool_calls_this_turn = 0

    while tool_calls_this_turn < MAX_TOOL_CALLS_PER_TURN:
        llm_response = chat_with_ollama(messages)

        func_name, kwargs = parse_tool_call(llm_response)

        if func_name is None:
            # No tool call — this is the final answer, stream it
            # Since we already got the response non-streamed for parsing,
            # just print it directly
            print(f"\n🤖 {llm_response}")
            conversation_history.append({"role": "assistant", "content": llm_response})
            return llm_response

        # Tool call detected
        tool_calls_this_turn += 1
        print(f"\n🔧 Calling tool: {func_name}({kwargs})")

        # Write operation — confirm with user
        if func_name in WRITE_TOOLS:
            if not confirm_write(func_name, kwargs):
                decline_msg = f"User declined the {func_name} operation."
                print(f"   ❌ {decline_msg}")
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({"role": "user", "content": f"[TOOL DECLINED] {decline_msg}"})
                conversation_history.append({"role": "assistant", "content": llm_response})
                conversation_history.append({"role": "user", "content": f"[TOOL DECLINED] {decline_msg}"})
                continue

        # Execute the tool
        result = execute_tool(func_name, kwargs)
        print(f"   ✅ Tool result received ({len(result)} chars)")

        # Feed result back to LLM
        messages.append({"role": "assistant", "content": llm_response})
        messages.append({"role": "user", "content": f"[TOOL RESULT for {func_name}]\n{result}"})

    # If we hit max tool calls, get a final response
    messages.append({"role": "user", "content": "[SYSTEM] Maximum tool calls reached. Please summarize what you have so far."})
    final = chat_with_ollama(messages)
    print(f"\n🤖 {final}")
    conversation_history.append({"role": "assistant", "content": final})
    return final


def main():
    print("=" * 60)
    print("  Zeal Jira Assistant (local, powered by llama3.2)")
    print("  Type 'quit' or 'exit' to stop. Type 'clear' to reset.")
    print("=" * 60)

    # Load recent memory context
    recent_context = load_recent_context(days=3)
    conversation_history = []
    if recent_context:
        conversation_history.append({
            "role": "system",
            "content": f"[MEMORY] Recent context from past sessions:\n{recent_context}",
        })

    while True:
        try:
            user_input = input("\n📝 You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break
        if user_input.lower() == "clear":
            conversation_history.clear()
            print("Conversation cleared.")
            continue

        response = run_react_turn(user_input, conversation_history)
        save_query_log(user_input, response)

        # Keep conversation history manageable (last 20 messages)
        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]


if __name__ == "__main__":
    main()
