"""
Intent-driven search endpoint for CloudMarket.

Pipeline:
1. Validate the incoming query (max 300 chars)
2. Embed the query with gemini-embedding-2 (Redis cache first)
3. Vector search using pgvector CosineDistance
4. Filter by similarity threshold (discard irrelevant matches)
5. Generate an LLM explanation (Redis cache first; graceful degradation if it fails)
6. Return structured JSON: { apps, explanation, error, mode }

Fallback: if the query can't be embedded (Gemini down, timed out, rate-limited)
or no apps are indexed yet, search falls back to Postgres full-text search and
the response says "mode": "keyword" instead of "semantic".

Every response carries a Server-Timing header with per-stage durations.
"""

import logging

import httpx
from django.conf import settings
from django.db import connection
from google.genai import errors as genai_errors
from pgvector.django import CosineDistance
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from marketplace.api.serializers import (
    IntentSearchAppSerializer,
    IntentSearchRequestSerializer,
)
from marketplace.models import Application
from marketplace.observability import StageTimer
from marketplace.services import cache
from marketplace.services.embedding import EMBEDDING_DIMENSIONS, generate_query_embedding
from marketplace.services.faults import InjectedFault
from marketplace.services.keyword_search import keyword_search
from marketplace.services.llm import generate_explanation

logger = logging.getLogger(__name__)

# Cosine distance threshold for relevance filtering.
# CosineDistance = 1 - cosine_similarity
# So distance 0.0 = identical, 1.0 = orthogonal, 2.0 = opposite.
# A threshold of 0.7 means: only return apps with cosine_similarity > 0.3
# Tune this based on testing with your actual catalog.
SIMILARITY_THRESHOLD = 0.7

# Maximum number of results to return
MAX_RESULTS = 5

NO_RESULTS_MESSAGE = (
    "We couldn't find apps matching your search. "
    "Try rephrasing or describing what you'd like to accomplish."
)
UNAVAILABLE_MESSAGE = (
    "Our AI search is temporarily unavailable. "
    "Please try again in a moment."
)
NOT_INDEXED_MESSAGE = (
    "AI search is still setting up. "
    "Apps are being indexed — please try again in a moment."
)


def _failure_reason(exc):
    """Short label for logs: why semantic search could not run."""
    if isinstance(exc, InjectedFault):
        return "injected"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(exc, genai_errors.APIError):
        return f"http_{exc.code}"
    return "error"


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def intent_search(request):
    """
    Search for apps using natural language intent.

    POST /api/search/
    Body: { "query": "I want to learn guitar as a beginner" }

    Response: {
        "apps": [ { app fields... }, ... ],
        "explanation": "We found 2 apps for learning guitar...",
        "error": null,
        "mode": "semantic"        # or "keyword" when the fallback served it
    }
    """
    serializer = IntentSearchRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {
                'apps': [],
                'explanation': None,
                'error': 'Please enter a valid search query (1-300 characters).',
                'mode': None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    query = serializer.validated_data['query'].strip()
    timer = StageTimer()
    log = {'mode': None, 'reason': None, 'embed_cache': None, 'expl_cache': None}

    # Connection setup is invisible to the query timer, so time it separately.
    with timer.stage('connect'):
        connection.ensure_connection()

    with timer.track_db():
        data = _search(query, timer, log)

    response = Response(data)
    response['Server-Timing'] = timer.header()
    logger.info(
        "search mode=%s reason=%s embed_cache=%s expl_cache=%s apps=%d timing=[%s]",
        log['mode'], log['reason'], log['embed_cache'], log['expl_cache'],
        len(data['apps']), response['Server-Timing'],
    )
    return response


def _search(query, timer, log):
    fallback_enabled = settings.SEARCH_FALLBACK_ENABLED

    # ── Step 1: Are any apps indexed for semantic search? ───────────────
    # exists() stops at the first row; a count() would scan the table.
    if not Application.objects.exclude(embedding__isnull=True).exists():
        if not fallback_enabled:
            log['mode'] = 'semantic'
            return _result([], None, NOT_INDEXED_MESSAGE, 'semantic')
        return _keyword(query, timer, log, reason='not_indexed')

    # ── Step 2: Embed the query (cache first) ───────────────────────────
    key = cache.embedding_key(query, settings.GEMINI_EMBEDDING_MODEL, EMBEDDING_DIMENSIONS)
    with timer.stage('cache'):
        query_embedding = cache.get_embedding(key)
    log['embed_cache'] = 'hit' if query_embedding is not None else 'miss'
    timer.notes['cache'] = log['embed_cache']

    if query_embedding is None:
        try:
            with timer.stage('embed'):
                query_embedding = generate_query_embedding(query)
        except Exception as exc:
            if not fallback_enabled:
                logger.exception("Embedding API failure during search")
                log['mode'], log['reason'] = 'semantic', _failure_reason(exc)
                return _result([], None, UNAVAILABLE_MESSAGE, 'semantic')
            logger.warning("Semantic search unavailable (%s); falling back to keyword search", exc)
            return _keyword(query, timer, log, reason=_failure_reason(exc))
        with timer.stage('cache'):
            cache.set_embedding(key, query_embedding, settings.EMBED_CACHE_TTL)

    # ── Step 3: Vector similarity search ────────────────────────────────
    log['mode'] = 'semantic'
    results = list(
        Application.objects
        .exclude(embedding__isnull=True)
        .select_related('developer')
        .prefetch_related('categories', 'os')
        .annotate(distance=CosineDistance('embedding', query_embedding))
        .filter(distance__lt=SIMILARITY_THRESHOLD)
        .order_by('distance')[:MAX_RESULTS]
    )
    if not results:
        return _result([], NO_RESULTS_MESSAGE, None, 'semantic')

    # ── Step 4: LLM explanation (cache first, graceful degradation) ─────
    explanation_key = cache.explanation_key(
        query, settings.GEMINI_INFERENCE_MODEL, [app.pk for app in results]
    )
    with timer.stage('cache'):
        explanation = cache.get_text(explanation_key)
    log['expl_cache'] = 'hit' if explanation else 'miss'

    if explanation is None:
        try:
            with timer.stage('llm'):
                explanation = generate_explanation(query, results)
        except Exception:
            # The user still gets results, just no AI summary
            logger.exception("LLM failure during search — returning apps without explanation")
            explanation = None
        if explanation:  # never cache a failure
            with timer.stage('cache'):
                cache.set_text(explanation_key, explanation, settings.EXPL_CACHE_TTL)

    return _result(results, explanation, None, 'semantic')


def _keyword(query, timer, log, reason):
    """Full-text fallback. Skips the LLM: Gemini is likely down, so don't wait on it again."""
    log['mode'], log['reason'] = 'keyword', reason
    with timer.stage('keyword'):
        results = keyword_search(query, MAX_RESULTS)
    if not results:
        return _result([], NO_RESULTS_MESSAGE, None, 'keyword')
    return _result(results, None, None, 'keyword')


def _result(apps, explanation, error, mode):
    return {
        'apps': IntentSearchAppSerializer(apps, many=True).data if apps else [],
        'explanation': explanation,
        'error': error,
        'mode': mode,
    }
