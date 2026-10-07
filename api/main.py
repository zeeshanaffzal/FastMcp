from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from agent.graph import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.graph = await build_graph()
    yield


app = FastAPI(title="MCP Demo", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat(req: ChatRequest):
    result = await app.state.graph.ainvoke({"messages": [("user", req.message)]})
    messages = result["messages"]
    # Show which MCP tools were called, useful for learning.
    tool_calls = [
        {"name": c["name"], "args": c["args"]}
        for m in messages
        for c in getattr(m, "tool_calls", [])
    ]
    return {"answer": messages[-1].text, "tool_calls": tool_calls}
