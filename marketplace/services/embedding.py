"""
Embedding service for CloudMarket semantic search.

Uses Google's gemini-embedding-2 model with asymmetric retrieval formatting:
- Documents (app profiles): "title: {name} | text: {description}..."
- Queries (user search):    "task: search result | query: {user input}"

The asymmetric format tells the model that queries and documents serve
different roles in retrieval, improving match quality.
"""

import logging

from google import genai
from google.genai import types
from django.conf import settings

logger = logging.getLogger(__name__)

# Lazy-initialized client (avoids import-time errors if API key isn't set yet)
_client = None

EMBEDDING_MODEL = getattr(settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIMENSIONS = 768


def _get_client():
    """Get or create the Gemini API client."""
    global _client
    if _client is None:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Add it to your .env file. "
                "Get a key at https://aistudio.google.com/apikey"
            )
        _client = genai.Client(api_key=api_key)
    return _client


def generate_app_embedding(app) -> list[float]:
    """
    Generate a 768-dimensional embedding for an Application instance.

    Uses the DOCUMENT format for asymmetric retrieval:
        title: {app_name} | text: {description}. Categories: ... Compatible with: ...

    Args:
        app: An Application model instance. Must have `categories` and `os`
             prefetched or accessible via related manager.

    Returns:
        A list of 768 floats representing the embedding vector.

    Raises:
        google.genai.errors.ClientError: If the API call fails.
        ValueError: If GEMINI_API_KEY is not configured.
    """
    # Build the category and OS strings
    categories = ", ".join(c.category_name for c in app.categories.all())
    os_list = ", ".join(o.os_name for o in app.os.all())

    # Construct the document text using asymmetric retrieval format
    # See: https://ai.google.dev/gemini-api/docs/embeddings#task-types-embeddings-2
    description = app.app_description or ""
    text = (
        f"title: {app.app_name} | text: {description}. "
        f"Categories: {categories or 'none'}. "
        f"Compatible with: {os_list or 'any'}"
    )

    logger.debug(f"Generating embedding for app '{app.app_name}': {text[:100]}...")

    client = _get_client()
    model = getattr(settings, "GEMINI_EMBEDDING_MODEL", EMBEDDING_MODEL)
    result = client.models.embed_content(
        model=model,
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )

    return result.embeddings[0].values


def generate_query_embedding(query: str) -> list[float]:
    """
    Generate a 768-dimensional embedding for a user's search query.

    Uses the QUERY format for asymmetric retrieval:
        task: search result | query: {user's natural language input}

    Args:
        query: The user's natural language search string.
               e.g. "I want to learn guitar as a beginner"

    Returns:
        A list of 768 floats representing the embedding vector.

    Raises:
        google.genai.errors.ClientError: If the API call fails.
        ValueError: If GEMINI_API_KEY is not configured.
    """
    # Construct the query text using asymmetric retrieval format
    text = f"task: search result | query: {query}"

    logger.debug(f"Generating query embedding: {text[:100]}...")

    client = _get_client()
    model = getattr(settings, "GEMINI_EMBEDDING_MODEL", EMBEDDING_MODEL)
    result = client.models.embed_content(
        model=model,
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )

    return result.embeddings[0].values
