import os

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

load_dotenv()

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8001/mcp")
MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")


async def build_graph():
    # 1. Connect to the MCP server and turn its tools into LangChain tools.
    client = MultiServerMCPClient(
        {"demo": {"url": MCP_URL, "transport": "streamable_http"}}
    )
    tools = await client.get_tools()

    # 2. LLM that knows about those tools.
    # OpenRouter exposes an OpenAI-compatible API.
    llm = ChatOpenAI(
        model=MODEL,
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    ).bind_tools(tools)

    async def agent(state: MessagesState):
        return {"messages": [await llm.ainvoke(state["messages"])]}

    # 3. Graph:  START -> agent -> (tool call?) -> tools -> agent ... -> END
    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
    return builder.compile()
