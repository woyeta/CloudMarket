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

logger = logging.getLogger(__name__)

_client = None

LLM_MODEL = getattr(settings, "GEMINI_INFERENCE_MODEL", "gemini-2.0-flash")


def _get_client():
    """Get or create the Gemini API client (shared with embedding service)."""
    global _client
    if _client is None:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Add it to your .env file."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def generate_explanation(query: str, apps) -> str:
    """
    Generate a 1-2 sentence explanation of why matched apps fit the user's query.

    Args:
        query: The user's original search string.
        apps:  A list/queryset of Application instances that matched.

    Returns:
        A string containing the 1-2 sentence explanation.

    Raises:
        google.genai.errors.ClientError: If the API call fails.
        ValueError: If GEMINI_API_KEY is not configured.
    """
    # Build a concise summary of each matched app for the prompt
    app_summaries = "\n".join(
        f"- {app.app_name}: {app.app_description or 'No description'}"
        for app in apps
    )

    prompt = (
        f'A user searched a software marketplace with the query: "{query}"\n\n'
        f"The following apps were returned as matches:\n"
        f"{app_summaries}\n\n"
        f"Write a brief 1-2 sentence summary explaining how these apps relate "
        f"to what the user is looking for. Be concise, specific, and helpful. "
        f"Do not mention any apps that are not in the list above. "
        f"Do not use markdown formatting."
    )

    logger.debug(f"LLM prompt ({len(prompt)} chars): {prompt[:200]}...")

    client = _get_client()
    response = client.models.generate_content(
        model=getattr(settings, "GEMINI_INFERENCE_MODEL", LLM_MODEL),
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=150,
        ),
    )

    explanation = response.text.strip()
    logger.debug(f"LLM response: {explanation}")

    return explanation
