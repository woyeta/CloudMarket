"""
Intent-driven search endpoint for CloudMarket.

Pipeline:
1. Validate the incoming query (max 300 chars)
2. Check if the catalog is empty → short-circuit with friendly message
3. Embed the query using gemini-embedding-2 (query format)
4. Vector search using pgvector CosineDistance
5. Filter by similarity threshold (discard irrelevant matches)
6. Generate LLM explanation for matched apps (graceful degradation if LLM fails)
7. Return structured JSON: { apps: [...], explanation: "...", error: null }
"""

import logging

from rest_framework.decorators import api_view, throttle_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.response import Response
from rest_framework import status

from pgvector.django import CosineDistance

from marketplace.models import Application
from marketplace.api.serializers import (
    IntentSearchRequestSerializer,
    IntentSearchAppSerializer,
)
from marketplace.services.embedding import generate_query_embedding
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

    # ── Step 1: Validate input ──────────────────────────────────────────
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

    # ── Step 2: Check for empty catalog ─────────────────────────────────
    if not Application.objects.exists():
        return Response({
            'apps': [],
            'explanation': None,
            'error': 'There are no apps in the marketplace yet. Check back soon!',
        })

    # Check if any apps have embeddings (might have apps but none indexed yet)
    indexed_count = Application.objects.exclude(embedding__isnull=True).count()
    if indexed_count == 0:
        return Response({
            'apps': [],
            'explanation': None,
            'error': (
                'AI search is still setting up. '
                'Apps are being indexed — please try again in a moment.'
            ),
        })

    # ── Step 3: Embed the query ─────────────────────────────────────────
    try:
        query_embedding = generate_query_embedding(query)
    except Exception:
        logger.exception("Embedding API failure during search")
        return Response({
            'apps': [],
            'explanation': None,
            'error': (
                'Our AI search is temporarily unavailable. '
                'Please try again in a moment.'
            ),
        })

    # ── Step 4: Vector similarity search ────────────────────────────────
    results = list(
        Application.objects
        .exclude(embedding__isnull=True)
        .select_related('developer')
        .prefetch_related('categories', 'os')
        .annotate(distance=CosineDistance('embedding', query_embedding))
        .filter(distance__lt=SIMILARITY_THRESHOLD)
        .order_by('distance')[:MAX_RESULTS]
    )

    # ── Step 5: No relevant results ─────────────────────────────────────
    if not results:
        return Response({
            'apps': [],
            'explanation': (
                "We couldn't find apps matching your search. "
                "Try rephrasing or describing what you'd like to accomplish."
            ),
            'error': None,
        })

    # ── Step 6: Serialize matched apps ──────────────────────────────────
    serialized_apps = IntentSearchAppSerializer(results, many=True).data

    # ── Step 7: Generate LLM explanation (graceful degradation) ─────────
    try:
        explanation = generate_explanation(query, results)
    except Exception:
        logger.exception(
            "LLM failure during search — returning apps without explanation"
        )
        # Graceful degradation: return apps without explanation
        # The user still gets useful results, just no AI summary
        explanation = None

    # ── Step 8: Return response ─────────────────────────────────────────
    return Response({
        'apps': serialized_apps,
        'explanation': explanation,
        'error': None,
    })
