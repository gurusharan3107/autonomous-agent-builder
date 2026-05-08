"""One-off, idempotent DB migrations executed at init_db().

Each module exposes a single async ``apply(conn)`` coroutine that uses
``CREATE ... IF NOT EXISTS`` style statements so reruns are safe.
"""
