# MCP Demo

A small project for learning the Model Context Protocol (MCP). A FastAPI backend sends chat messages to a LangGraph agent. The agent uses an LLM (via OpenRouter) and calls tools hosted on a FastMCP server.

## Project structure

```
mcp-demo/
├── api/
│   └── main.py          # FastAPI app: POST /chat
├── agent/
│   └── graph.py         # LangGraph agent + MCP client + LLM
├── mcp_server/
│   └── server.py        # FastMCP server: tools, resource, prompt
├── requirements.txt
└── .env                 # API key, model, MCP URL
```

| Component | Role | Tech |
|-----------|------|------|
| `api/main.py` | HTTP entry point. Builds the agent once at startup and exposes `/chat`. | FastAPI |
| `agent/graph.py` | Loads tools from the MCP server and runs the LLM/tool loop. | LangGraph, langchain-mcp-adapters, langchain-openai |
| `mcp_server/server.py` | Hosts the tools the agent can call. Runs as its own process. | FastMCP |
| OpenRouter | The LLM provider (free model). | OpenAI-compatible API |

## Architecture

```
┌────────┐  POST /chat   ┌──────────────┐        ┌───────────────────────┐
│ Client │ ────────────► │  FastAPI     │ ─────► │  LangGraph agent      │
│ (curl) │ ◄──────────── │  :8000       │ ◄───── │  (agent/graph.py)     │
└────────┘   answer +    └──────────────┘        └───────┬───────┬───────┘
             tool_calls                                  │       │
                                          chat completions│       │ MCP (streamable HTTP)
                                                         ▼       ▼
                                                 ┌────────────┐ ┌──────────────────┐
                                                 │ OpenRouter │ │ FastMCP server   │
                                                 │ (LLM)      │ │ :8001/mcp        │
                                                 └────────────┘ │ add, get_weather │
                                                                └──────────────────┘
```

Two separate processes run: the FastAPI app (port 8000) and the MCP server (port 8001). The agent connects to the MCP server over HTTP, so tools could live on any machine or be written in any language.

## Request flow

1. The client sends `POST /chat` with `{"message": "..."}`.
2. FastAPI passes the message to the compiled LangGraph graph.
3. **agent node**: the LLM receives the conversation plus the list of MCP tool schemas. It either answers or asks to call a tool.
4. If it asked for a tool, the **tools node** sends the call to the MCP server, which runs the function and returns the result.
5. The result is added to the conversation and control returns to the agent node (step 3). This repeats until the LLM answers without calling a tool.
6. FastAPI returns the final `answer` and the list of `tool_calls` that were made.

```
START ──► agent ──► tool call requested? ──yes──► tools ──┐
            ▲                  │                          │
            │                  no                         │
            │                  ▼                          │
            └──────────────────END ◄──────────────────────┘
                     (loops back to agent after tools)
```

At startup (not per request), `build_graph()` connects to the MCP server, fetches the tool list (`client.get_tools()`), and converts them into LangChain tools. This is why the MCP server must be running before the API starts.

## MCP concepts shown here

| MCP primitive | Example in `server.py` | Who uses it |
|---------------|------------------------|-------------|
| Tool | `add`, `get_weather` | The LLM (model-controlled). The agent uses these. |
| Resource | `info://about` | The client application (read-only data by URI) |
| Prompt | `summarize` | The user/client (reusable prompt templates) |

The agent in this project only uses tools. You can see resources and prompts with the MCP Inspector (see below).

## Installation

Requirements: Python 3.10+ and an OpenRouter account.

```bash
cd mcp-demo

# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a key at https://openrouter.ai/keys and edit `.env`:

```
OPENROUTER_API_KEY=your-key-here
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
MCP_URL=http://127.0.0.1:8001/mcp
```

The model must support tool calling. If you get a "no endpoints found that support tool use" error, pick another model at https://openrouter.ai/models (filter by Free price and the "tools" parameter). Free models are rate-limited, so 429 errors are normal; wait or switch models.

Do not commit `.env`.

## Running

Use two terminals, both with the virtual environment active, from the `mcp-demo/` directory.

```bash
# Terminal 1: MCP server (start this first)
python -m mcp_server.server

# Terminal 2: API
uvicorn api.main:app --reload
```

## Try it

```bash
curl -X POST localhost:8000/chat \
  -H 'content-type: application/json' \
  -d '{"message": "What is 17 + 25, and what is the weather in Paris?"}'
```

Expected response shape:

```json
{
  "answer": "17 + 25 is 42, and it is 24°C and sunny in Paris.",
  "tool_calls": [
    {"name": "add", "args": {"a": 17, "b": 25}},
    {"name": "get_weather", "args": {"city": "Paris"}}
  ]
}
```

The `tool_calls` field shows the tools that were called through MCP. Interactive API docs are at http://localhost:8000/docs.

### Inspect the MCP server directly

```bash
npx @modelcontextprotocol/inspector
```

Choose transport "Streamable HTTP" and URL `http://127.0.0.1:8001/mcp`. You can list and call tools, read the resource, and render the prompt without any LLM.

## Slack tools

The MCP server has two Slack tools: `send_slack_message` and `read_slack_messages`. The agent picks them up automatically.

1. Create an app at https://api.slack.com/apps (From scratch).
2. Under *OAuth & Permissions*, add the Bot Token Scopes `chat:write`, `channels:read`, `channels:history` (add `groups:read` and `groups:history` for private channels).
3. Click *Install to Workspace* and copy the Bot User OAuth Token (`xoxb-...`) into `.env` as `SLACK_BOT_TOKEN`.
4. In Slack, invite the bot to a channel: `/invite @YourBot`.
5. Restart the MCP server and the API.

Try it:

```bash
curl -X POST localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message": "Send a message to #general saying hello from MCP"}'
```

Without a valid token, the tools return an error such as `invalid_auth` and the rest of the server still works.

## Extending it

Add a tool in `mcp_server/server.py`, restart the MCP server, then restart the API:

```python
@mcp.tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b
```

No agent code changes are needed. The agent discovers tools from the server at startup. The docstring and type hints become the tool description that the LLM sees, so write them clearly.

## Troubleshooting

| Problem | Cause / fix |
|---------|-------------|
| API fails at startup with a connection error | The MCP server isn't running. Start it first. |
| `ModuleNotFoundError: agent` | Run commands from the `mcp-demo/` directory. |
| `KeyError: OPENROUTER_API_KEY` | `.env` is missing or the key isn't set. |
| Error about tool use not supported | Choose a different free model that supports tools. |
| 429 errors | Free model rate limit. Wait or switch models. |
| Tool changes not showing up | Restart both the MCP server and the API. |
