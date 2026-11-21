"""Lets CrewAI talk to Groq through our own Groq service (no LiteLLM needed)."""
from crewai import BaseLLM

from config.settings import get_settings
from services.llm_service import LLMService


class GroqCrewLLM(BaseLLM):
    def __init__(self, temperature: float = 0.1):
        settings = get_settings()
        super().__init__(model=settings.groq_model, temperature=temperature)
        self._service = LLMService()

    def call(self, messages, tools=None, callbacks=None, available_functions=None,
             from_task=None, from_agent=None, **kwargs):
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        text = self._service.chat(messages, temperature=self.temperature)
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
