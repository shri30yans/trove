"""Domain vocabularies. Postgres owns the enums; this package mirrors them in one place.

Every module that needs a kind, a status, a score weight or a threshold imports it from one of
these submodules, so a value exists exactly once in Python.

tests/test_domain_enums.py asserts app.domain.enums equals the CREATE TYPE labels in
migrations/, which is the only automated guard that keeps the two in step.
"""
