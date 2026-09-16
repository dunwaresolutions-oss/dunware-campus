"""
Shared free-text "q=" search helper.

Every list endpoint's `?q=` search used to build its filter as
`Q(field_a__icontains=q) | Q(field_b__icontains=q) | ...` - one field
checked against the *whole* query string. That only ever matches a
single-word query (or a query that happens to fit inside one field): a
person's name is usually split across `first_name`/`last_name`, so
searching "Uriah Oliver" never matched a student named exactly that -
neither column alone contains the two-word string. Found 2026-09-16
(Damien: an issued invoice existed for "Uriah Oliver" but the universal
search couldn't find him) and fixed there first (`apps/core/search.py`);
this is the same fix shared across every other `?q=` search that had the
identical pattern.
"""
from __future__ import annotations

from django.db.models import Q


def multi_word_icontains(query: str, fields: list[str]) -> Q:
    """AND across the words in `query`, OR across `fields` per word - so
    "First Last" matches a person whose name is split across two columns,
    while a bare single-word query still behaves exactly like the old
    `Q(field_a__icontains=q) | Q(field_b__icontains=q) | ...` it replaces.
    The AND is evaluated per row (a single Q object, not separate
    `.filter()` calls), so "Uriah Oliver" can't cross-match an unrelated
    "Uriah Adderley" and a different "Marcus Oliver" just because each
    word appears somewhere in the table.

    An empty/whitespace `query` returns `Q()` (matches everything, same
    as omitting the filter) - callers already only apply this when `q` is
    truthy, so this is a defensive default, not the expected path."""
    combined = Q()
    for word in query.split():
        word_q = Q()
        for field in fields:
            word_q |= Q(**{f"{field}__icontains": word})
        combined &= word_q
    return combined
