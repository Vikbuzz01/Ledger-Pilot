"""Provider abstraction with an optional OpenAI-compatible JSON endpoint."""

import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings
from app.modules.reconciliation.investigation.evaluators import evaluate_report
from app.modules.reconciliation.investigation.prompts import SYSTEM_PROMPT
from app.modules.reconciliation.investigation.schemas import (
    InvestigationReport,
    ProviderUnavailable,
)


class ModelProvider(Protocol):
    def investigate(self, context: dict) -> InvestigationReport: ...


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model

    def investigate(self, context: dict) -> InvestigationReport:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, default=str)},
            ],
        }
        request = Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                data = json.loads(response.read())
            text = data["choices"][0]["message"]["content"]
            report = InvestigationReport.model_validate_json(text)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            KeyError,
            IndexError,
            ValueError,
            TypeError,
        ) as exc:
            raise RuntimeError("AI provider call or structured output validation failed") from exc
        return evaluate_report(report, context)


def configured_provider() -> ModelProvider:
    settings = get_settings()
    if settings.ai_provider.casefold() in {"none", ""} or settings.ai_api_key is None:
        raise ProviderUnavailable("AI provider is not configured")
    if settings.ai_provider.casefold() != "openai_compatible":
        raise ProviderUnavailable("Configured AI provider is unsupported")
    return OpenAICompatibleProvider(
        settings.ai_base_url, settings.ai_api_key.get_secret_value(), settings.ai_model
    )
