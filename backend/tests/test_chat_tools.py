from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from app.services.chat_service import _build_chatbot


class FakeToolCallingModel:
    def __init__(self) -> None:
        self.bound_tools: list[str] = []

    def bind_tools(self, tools):
        self.bound_tools = [item.name for item in tools]
        return self

    def invoke(self, messages):
        if any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(content="Current result: https://example.com")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "web_search",
                    "args": {"query": "latest news"},
                    "id": "search-1",
                    "type": "tool_call",
                }
            ],
        )


def test_chatbot_executes_search_tool_before_answering() -> None:
    @tool
    def web_search(query: str) -> str:
        """Search the web for current information."""
        return f"Search results for {query}: https://example.com"

    model = FakeToolCallingModel()
    chatbot = _build_chatbot(model, [web_search])

    result = chatbot.invoke({"messages": [HumanMessage(content="What is current?")]})

    assert model.bound_tools == ["web_search"]
    assert any(
        isinstance(message, ToolMessage)
        and "Search results for latest news" in message.content
        for message in result["messages"]
    )
    assert result["messages"][-1].content == "Current result: https://example.com"
