"""Lets CrewAI talk to Groq through our own Groq service (no LiteLLM needed)."""
from crewai import BaseLLM

from config.settings import get_settings
from services.llm_service import LLMService


def _clean_messages(messages) -> list:
    """Groq accepts only simple messages: a role and a plain text content."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]

    cleaned = []
    for message in messages:
        if isinstance(message, dict):
            role, content = message.get("role", "user"), message.get("content")
        else:
            role, content = "user", message

        if isinstance(content, list):  # some versions send a list of text blocks
            content = "\n".join(
                str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content
            )
        content = "" if content is None else str(content)

        if role not in ("system", "user", "assistant"):
            role = "user"
        if content.strip():
            cleaned.append({"role": role, "content": content})

    if not cleaned:
        cleaned = [{"role": "user", "content": "Hello"}]
    if cleaned[-1]["role"] == "assistant":
        cleaned.append({"role": "user", "content": "Please give your final answer now."})
    return cleaned


class GroqCrewLLM(BaseLLM):
    def __init__(self, temperature: float = 0.1):
        settings = get_settings()
        super().__init__(model=settings.groq_model, temperature=temperature)
        self._service = LLMService()

    def call(self, messages, tools=None, callbacks=None, available_functions=None,
             from_task=None, from_agent=None, **kwargs):
        text = self._service.chat(_clean_messages(messages), temperature=self.temperature)
        # CrewAI's text mode looks for "Final Answer:". Adding it avoids pointless retry loops.
        if "Final Answer:" not in text:
            text = "Thought: I now can give a great answer\nFinal Answer: " + text
        return text

    async def acall(self, messages, tools=None, callbacks=None, available_functions=None,
                    from_task=None, from_agent=None, **kwargs):
        return self.call(messages, tools, callbacks, available_functions, from_task, from_agent)

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 100000
