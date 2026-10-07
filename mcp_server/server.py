import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

mcp = FastMCP("demo-server")


def _slack() -> WebClient:
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        raise ToolError("SLACK_BOT_TOKEN is not set in .env")
    return WebClient(token=token)


# Tools: actions the LLM can call.
@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@mcp.tool
def get_weather(city: str) -> str:
    """Get the (fake) current weather for a city."""
    return f"It is 24°C and sunny in {city}."


@mcp.tool
def send_slack_message(channel: str, text: str) -> str:
    """Send a message to a Slack channel. `channel` is a name like '#general' or a channel ID.
    The bot must be invited to the channel first."""
    try:
        r = _slack().chat_postMessage(channel=channel, text=text)
    except SlackApiError as e:
        raise ToolError(f"Slack error: {e.response['error']}")
    return f"Message sent to {channel} (ts={r['ts']})"


@mcp.tool
def read_slack_messages(channel_id: str, limit: int = 10) -> list[str]:
    """Read the latest messages (newest first) from a Slack channel by its channel ID (e.g. 'C0123ABC')."""
    try:
        r = _slack().conversations_history(channel=channel_id, limit=limit)
    except SlackApiError as e:
        raise ToolError(f"Slack error: {e.response['error']}")
    return [m.get("text", "") for m in r["messages"]]


# Resources: read-only data the client can fetch by URI.
@mcp.resource("info://about")
def about() -> str:
    return "This is a demo MCP server built with FastMCP."


# Prompts: reusable prompt templates.
@mcp.prompt
def summarize(text: str) -> str:
    return f"Summarize the following text in one sentence:\n\n{text}"


if __name__ == "__main__":
    # Streamable HTTP endpoint -> http://127.0.0.1:8001/mcp
    mcp.run(transport="http", host="127.0.0.1", port=8001)
