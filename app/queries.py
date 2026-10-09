"""SQL fragments more than one route has to spell identically.

Only fragments that are byte-for-byte the same query belong here. Two statements that do nearly the
same thing in different shapes stay where they are, because forcing them into one parameterised
fragment makes both of them harder to read than the duplication they replace.

Every fragment is spliced into an f-string SQL, and `tests/test_sql_tenant_scope.py` only allows an
ALL_CAPS constant there — nothing a caller can influence may be spliced into statement text. So a
fragment that correlates on a row keeps that row's alias as part of its contract, and the query that
uses it names the row accordingly.
"""

from __future__ import annotations

# The first attached asset by position, as the Storage key a preview URL is minted from. The list,
# search, related and resurfacing queries all answer "what is this Memory's thumbnail", and none of
# them should drift into giving a different one. It correlates on the memories row being aliased `m`.
PREVIEW_KEY_SUBQUERY = """(SELECT a.object_key FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id
                           WHERE ma.memory_id=m.id AND ma.user_id=m.user_id
                           ORDER BY ma.position LIMIT 1) AS preview_key"""
