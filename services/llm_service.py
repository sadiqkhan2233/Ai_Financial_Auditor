import logging
import time

from groq import APIConnectionError, APIStatusError, Groq, RateLimitError

from config.settings import get_settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """A friendly error we can show to the user."""


class LLMService:
    def __init__(self, api_key=None, model=None, max_retries=4):
        settings = get_settings()
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        self.max_retries = max_retries
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is missing. Add it in Streamlit Secrets.")
        self.client = Groq(api_key=self.api_key)

    def chat(self, messages: list, temperature: float | None = None) -> str:
        kwargs = {"messages": messages, "model": self.model}
        if temperature is not None:
            kwargs["temperature"] = temperature

        for attempt in range(1, self.max_retries + 1):
            try:
                result = self.client.chat.completions.create(**kwargs)
                return result.choices[0].message.content or ""
            except RateLimitError as err:
                logger.warning("Groq rate limit (attempt %s): %s", attempt, err)
                if attempt == self.max_retries:
                    raise LLMError(
                        "Groq says you have used your limit for now (free plans have per-minute limits). "
                        "Wait one minute and try again."
                    ) from err
                time.sleep(15 * attempt)
            except APIConnectionError as err:
                logger.warning("Groq connection problem (attempt %s): %s", attempt, err)
                if attempt == self.max_retries:
                    raise LLMError("Could not reach Groq. Please try again shortly.") from err
                time.sleep(2 ** attempt)
            except APIStatusError as err:
                logger.error("Groq error %s: %s", err.status_code, err)
                if err.status_code == 404:
                    raise LLMError(
                        f"Model '{self.model}' is not available. Change GROQ_MODEL in Streamlit Secrets."
                    ) from err
                if err.status_code in (401, 403):
                    raise LLMError("Groq rejected the API key. Please check it.") from err
                raise LLMError(f"Groq returned an error ({err.status_code}).") from err
        raise LLMError("Unexpected error while contacting Groq.")

    def ask(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)
