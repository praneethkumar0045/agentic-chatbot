from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage

from app.core import settings


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL or "gemini-3.5-flash",
    temperature=settings.LLM_TEMPERATURE,
    max_tokens=int(settings.MAX_OUTPUT_TOKENS) if settings.MAX_OUTPUT_TOKENS else None,
    timeout=None,
    max_retries=2,
)


def _chat_node(state: ChatState):
    return {"messages": [llm.invoke(state["messages"])]}


graph = StateGraph(ChatState)
graph.add_node("chat_node", _chat_node)
graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)

chatbot = graph.compile()


def _to_base_message(m):
    role = (m.role or "").lower()
    content = m.content or ""
    if role == "user":
        return HumanMessage(content=content)
    if role == "assistant" or role == "ai":
        return AIMessage(content=content)
    if role == "tool":
        return ToolMessage(content=content, tool_call_id="tool")
    if role == "system":
        return SystemMessage(content=content)
    return HumanMessage(content=content)


def chat(messages, thread_id: str):
    base_msgs = [_to_base_message(x) for x in messages]
    state = {"messages": base_msgs}
    result = chatbot.invoke(state)
    return result["messages"]


def stream_chat(messages, thread_id: str):
    base_msgs = [_to_base_message(x) for x in messages]
    state = {"messages": base_msgs}
    for message_chunk, metadata in chatbot.stream(
        state, stream_mode="messages"
    ):
        yield message_chunk
