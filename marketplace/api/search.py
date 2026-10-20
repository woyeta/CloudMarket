"""
Intent-driven search endpoint for CloudMarket.

Pipeline:
1. Validate the incoming query (max 300 chars)
2. Check if the catalog is empty → short-circuit with friendly message
3. Embed the query using gemini-embedding-2 (Redis cache first)
4. Vector search using pgvector CosineDistance
5. Filter by similarity threshold (discard irrelevant matches)
6. Generate LLM explanation (Redis cache first; graceful degradation if LLM fails)
7. Return structured JSON: { apps: [...], explanation: "...", error: null }

Every response carries a Server-Timing header with per-stage durations.
"""

import logging

from django.conf import settings
from django.db import connection
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
        "error": null
    }
    """
    serializer = IntentSearchRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {
                'apps': [],
                'explanation': None,
                'error': 'Please enter a valid search query (1-300 characters).',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    query = serializer.validated_data['query'].strip()
    timer = StageTimer()
    log = {'embed_cache': None, 'expl_cache': None}

    # Connection setup is invisible to the query timer, so time it separately.
    with timer.stage('connect'):
        connection.ensure_connection()

    with timer.track_db():
        data = _search(query, timer, log)

    response = Response(data)
    response['Server-Timing'] = timer.header()
    logger.info(
        "search embed_cache=%s expl_cache=%s apps=%d timing=[%s]",
        log['embed_cache'], log['expl_cache'], len(data['apps']), response['Server-Timing'],
    )
    return response


def _search(query, timer, log):
    # ── Step 1: Check for empty catalog ─────────────────────────────────
    if not Application.objects.exists():
        return _result([], None, 'There are no apps in the marketplace yet. Check back soon!')

    # Check if any apps have embeddings. exists() stops at the first row;
    # a count() would scan the whole table on every search.
    if not Application.objects.exclude(embedding__isnull=True).exists():
        return _result([], None, (
            'AI search is still setting up. '
            'Apps are being indexed — please try again in a moment.'
        ))

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
        except Exception:
            logger.exception("Embedding API failure during search")
            return _result([], None, (
                'Our AI search is temporarily unavailable. '
                'Please try again in a moment.'
            ))
        with timer.stage('cache'):
            cache.set_embedding(key, query_embedding, settings.EMBED_CACHE_TTL)

    # ── Step 3: Vector similarity search ────────────────────────────────
    results = list(
        Application.objects
        .exclude(embedding__isnull=True)
        .select_related('developer')
        .prefetch_related('categories', 'os')
        .annotate(distance=CosineDistance('embedding', query_embedding))
        .filter(distance__lt=SIMILARITY_THRESHOLD)
        .order_by('distance')[:MAX_RESULTS]
    )

    # ── Step 4: No relevant results ─────────────────────────────────────
    if not results:
        return _result([], (
            "We couldn't find apps matching your search. "
            "Try rephrasing or describing what you'd like to accomplish."
        ), None)

    # ── Step 5: LLM explanation (cache first, graceful degradation) ─────
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

    return _result(results, explanation, None)


def _result(apps, explanation, error):
    return {
        'apps': IntentSearchAppSerializer(apps, many=True).data if apps else [],
        'explanation': explanation,
        'error': error,
    }
