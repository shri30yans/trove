"""Every tenant table must be reached through a user_id predicate.

Ownership in this codebase is a SQL convention written into ~75 statements by hand, so one
omission is a cross-tenant read. This test is the guard: it walks the real AST of every module
under app/ and fails on any statement that touches a table without mentioning user_id. The
exemptions below are the only statements that legitimately have no tenant to filter on.
"""

from __future__ import annotations

import ast
import pathlib
import re

APP_ROOT = pathlib.Path(__file__).resolve().parent.parent / "app"

STATEMENT = re.compile(
    r"(\bSELECT\b[\s\S]*\bFROM\b|\bINSERT\s+INTO\b|\bUPDATE\s+\w+\s+SET\b|\bDELETE\s+FROM\b)",
    re.I,
)

# Whole modules that only administer the database or the session, never tenant rows.
EXEMPT_MODULES = {
    "main.py": "SELECT 1 pool liveness probe",
    "migrate.py": "DDL, schema_migrations and the advisory lock",
    "vector_search.py": "set_config of session-level pgvector tuning",
}

# Individual statements identified by a stable prefix of their text.
_APP_USERS_REASON = "app_users is keyed by auth_subject, which is the identity being resolved"
_APP_USER_ID_REASON = "the app_users row lock is scoped by the authenticated principal's internal user ID"
_AUTH_SUBJECT_REASON = "the verified Auth subject scopes account lifecycle state before an app user row exists"
_APP_USER_DELETE_REASON = "the internal user ID comes from the verified principal and scopes the cascade delete"
EXEMPT_STATEMENTS = {
    "INSERT INTO app_users": _APP_USERS_REASON,
    "SELECT id, email, display_name FROM app_users": _APP_USERS_REASON,
    "SELECT storage_plan FROM app_users": _APP_USER_ID_REASON,
    "DELETE FROM app_users WHERE id=": _APP_USER_DELETE_REASON,
    "SELECT 1 FROM deleted_auth_subjects": _AUTH_SUBJECT_REASON,
    "SELECT EXISTS(SELECT 1 FROM deleted_auth_subjects": _AUTH_SUBJECT_REASON,
    "WITH status AS ( SELECT EXISTS(SELECT 1 FROM deleted_auth_subjects": _AUTH_SUBJECT_REASON,
    "SELECT 1 FROM account_deletion_requests": _AUTH_SUBJECT_REASON,
    "SELECT requested_at,delete_after FROM account_deletion_requests": _AUTH_SUBJECT_REASON,
    "SELECT requested_at,delete_after,(delete_after > now()) AS deletion_cancellable": _AUTH_SUBJECT_REASON,
    "DELETE FROM account_deletion_requests": _AUTH_SUBJECT_REASON,
    "INSERT INTO deleted_auth_subjects": _AUTH_SUBJECT_REASON,
}


def _statements(path: pathlib.Path) -> list[tuple[int, str]]:
    """Every SQL string in the module, one entry per statement.

    An f-string statement is read as its literal parts joined together, since the clause that
    carries the tenant predicate can sit on either side of the fragment being spliced in.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    spliced = {
        id(node) for statement in ast.walk(tree) if isinstance(statement, ast.JoinedStr) for node in ast.walk(statement)
    }
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            text = "".join(
                part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in spliced:
            text = node.value
        else:
            continue
        if STATEMENT.search(text):
            found.append((node.lineno, " ".join(text.split())))
    return found


def _exemption_for(module_name: str, statement: str) -> str | None:
    if module_name in EXEMPT_MODULES:
        return EXEMPT_MODULES[module_name]
    for prefix, reason in EXEMPT_STATEMENTS.items():
        if statement.startswith(prefix):
            return reason
    return None


def test_every_app_module_was_scanned() -> None:
    modules = list(APP_ROOT.rglob("*.py"))
    assert len(modules) >= 20, f"expected the whole backend under {APP_ROOT}, found {len(modules)}"
    scanned = [path for path in modules if _statements(path)]
    assert len(scanned) >= 8, "the SQL detector found almost nothing, so it is probably broken"


def test_no_sql_interpolates_a_python_value() -> None:
    """Statement text may come from an ALL_CAPS column constant; nothing else may be spliced in.

    Everything a client can influence has to arrive as a $n parameter, so a call, a subscript or
    a lowercase local inside an f-string SQL is the shape of an injection.
    """
    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.JoinedStr) or not STATEMENT.search(_literal_text(node)):
                continue
            for part in node.values:
                if isinstance(part, ast.FormattedValue) and _interpolates_unsafe_name(part.value):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], f"SQL built from Python values at {sorted(set(offenders))}"


def _interpolates_unsafe_name(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return not node.id.isupper()
    if isinstance(node, ast.Attribute | ast.Subscript | ast.Call | ast.Starred):
        return True
    return any(_interpolates_unsafe_name(child) for child in ast.iter_child_nodes(node))


def _literal_text(node: ast.JoinedStr) -> str:
    return "".join(
        part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else "$" for part in node.values
    )


def test_every_statement_that_reads_a_table_filters_by_user_id() -> None:
    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path.name in EXEMPT_MODULES:
            continue
        for lineno, statement in _statements(path):
            if "user_id" in statement or _exemption_for(path.name, statement):
                continue
            offenders.append(f"{path.name}:{lineno}: {statement[:120]}")
    assert offenders == [], "statements without a tenant predicate:\n" + "\n".join(offenders)
