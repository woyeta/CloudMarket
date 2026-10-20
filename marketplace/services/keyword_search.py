"""
Postgres full-text search, used as the fallback when semantic search fails.

Matches the query's words against the app name (weight A) and description
(weight B) through the GIN-indexed `search_vector` column.

Words are OR-ed together: natural-language queries such as
"I want to learn guitar as a beginner" would match nothing if every word
were required. Each word goes through plainto_tsquery, so Postgres handles
stemming and stop words, and user input cannot inject tsquery operators.
"""

import operator
import re
from functools import reduce

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F

from marketplace.models import Application

_TERM = re.compile(r"\w+")
MAX_TERMS = 20


def keyword_search(query: str, limit: int):
    terms = _TERM.findall(query.lower())[:MAX_TERMS]
    if not terms:
        return []

    tsquery = reduce(operator.or_, (SearchQuery(term, config="english") for term in terms))

    return list(
        Application.objects
        .filter(search_vector=tsquery)
        .select_related("developer")
        .prefetch_related("categories", "os")
        .annotate(rank=SearchRank(F("search_vector"), tsquery))
        .order_by("-rank", "-downloads")[:limit]
    )
