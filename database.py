"""Two small database backends: local SQLite and Render PostgreSQL."""
import os
import re


def postgres_url():
    value = os.getenv("DATABASE_URL", "").strip()
    return value if value.startswith(("postgres://", "postgresql://")) else None


class PostgresConnection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, statement, parameters=()):
        # Our static queries use SQLite's ? placeholders; values remain bound.
        return self.raw.execute(statement.replace("?", "%s"), parameters)

    def executescript(self, script):
        # Only the application's fixed CREATE TABLE statements use this helper.
        for statement in script.replace(" REAL", " DOUBLE PRECISION").split(";"):
            if statement.strip():
                self.raw.execute(statement)


def open_postgres():
    import psycopg
    from psycopg.rows import dict_row
    options = {}
    schema = os.getenv("CAP_AVENIR_DB_SCHEMA")
    if schema:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", schema):
            raise ValueError("Invalid database schema name")
        options["options"] = "-c search_path=" + schema
    return psycopg.connect(postgres_url(), row_factory=dict_row, connect_timeout=10, **options)
