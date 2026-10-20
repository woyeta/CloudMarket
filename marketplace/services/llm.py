"""
LLM service for generating search result explanations.

Uses Gemini 2.0 Flash to produce a 1-2 sentence summary explaining
why the matched apps are relevant to the user's search query.

Example output:
    "We found 2 apps for learning guitar: GuitarTutor offers
     interactive chord lessons, while EarMaster focuses on
     ear-training for beginners."
"""

import logging

from google import genai
from google.genai import types
from django.conf import settings

from marketplace.services.faults import maybe_inject

logger = logging.getLogger(__name__)

_client = None

LLM_MODEL = getattr(settings, "GEMINI_INFERENCE_MODEL", "gemini-flash-lite-latest")


# The SDK sends our timeout to the API as the server-side deadline, and the
# API rejects deadlines under 10 s. Keep the shorter client-side timeout but
# send the minimum deadline the API accepts.
_MIN_SERVER_DEADLINE_S = 10


def _server_deadline_header(timeout_ms):
    if timeout_ms and timeout_ms < _MIN_SERVER_DEADLINE_S * 1000:
        return {"X-Server-Timeout": str(_MIN_SERVER_DEADLINE_S)}
    return None


def _get_client():
    """Get or create the Gemini API client (shared with embedding service)."""
    global _client
    if _client is None:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Add it to your .env file."
            )
        timeout_ms = getattr(settings, "GEMINI_LLM_TIMEOUT_MS", 0) or None
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=timeout_ms,
                headers=_server_deadline_header(timeout_ms),
            ),
        )
    return _client


def generate_explanation(query: str, apps) -> str:
    """
    Generate a 1-2 sentence explanation of why matched apps fit the user's query.

    Args:
        query: The user's original search string.
        apps:  A list/queryset of Application instances that matched.

    Returns:
        A string containing the 1-2 sentence explanation, or None if unavailable.

    Raises:
        google.genai.errors.ClientError: If the API call fails.
        ValueError: If GEMINI_API_KEY is not configured.
    """
    if not apps or not query:
        return None

    maybe_inject(getattr(settings, "GEMINI_LLM_TIMEOUT_MS", 0))

    # Build a concise summary of each matched app for the prompt
    app_summaries = "\n".join(
        f"- {app.app_name}: {app.app_description or 'No description'}"
        for app in apps
    )

    prompt = (
        f'A user searched a software marketplace with the query: "{query}"\n\n'
        f"The following apps were returned as matches:\n"
        f"{app_summaries}\n\n"
        f"Write a concise 1-2 sentence explanation of how the matched apps relate "
        f"to what the user is looking for. Focus on relevant apps and summarize what they offer. "
        f"Do not invent features or mention apps outside the list. "
        f"Do not use markdown formatting."
    )

    logger.debug(f"LLM prompt ({len(prompt)} chars): {prompt[:200]}...")

    client = _get_client()
    model = getattr(settings, "GEMINI_INFERENCE_MODEL", LLM_MODEL)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=500,
        ),
    )

    explanation = (response.text or "").strip() if (response and response.text) else None
    logger.debug(f"LLM response: {explanation}")

    return explanation
