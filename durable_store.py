"""Durable SQLite-image transactions in PostgreSQL for a small single-owner app.

This is a compatibility backend, not a relational schema migration: original
SQLite queries/settlement rules remain unchanged. PostgreSQL holds each sport's
database image and serialises transactions with a row lock. No silent local
fallback is allowed when remote storage fails. Large deployments should migrate
to normalised PostgreSQL tables; each transaction transfers a full database.
"""
from contextlib import contextmanager
import os
import sqlite3


class StorageUnavailable(RuntimeError):
    pass


def _remote_connect():
    try:
        import psycopg
        return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10,
                               sslmode="require", prepare_threshold=None)
    except Exception:
        raise StorageUnavailable("永久資料庫無法連線；請檢查 DATABASE_URL，未切換成臨時資料庫。") from None


@contextmanager
def database_connection(local_path, sport, *, read_only=False):
    if sport not in {"mlb", "football"}:
        raise ValueError("unknown database")
    if not os.environ.get("DATABASE_URL", "").strip():
        if os.environ.get("REQUIRE_DURABLE_STORAGE", "0") == "1":
            raise StorageUnavailable("尚未設定 DATABASE_URL；請先完成永久資料庫設定。")
        if read_only:
            from pathlib import Path
            conn = sqlite3.connect(Path(local_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        else:
            conn = sqlite3.connect(local_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()
        return
    # SQL setup is an explicit admin deployment step, not a member request.
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        with _remote_connect() as remote:
            remote.execute("SET LOCAL lock_timeout = '15s'")
            remote.execute("SET LOCAL statement_timeout = '30s'")
            row = remote.execute(
                "SELECT payload FROM dali_private.database_images WHERE sport=%s" + ("" if read_only else " FOR UPDATE"), (sport,)
            ).fetchone()
            if row is None:
                raise StorageUnavailable("永久資料庫尚未初始化；請執行 database_setup.sql。")
            before = bytes(row[0]) if row[0] else b""
            if before:
                conn.deserialize(before)
            if read_only:
                conn.execute("PRAGMA query_only=ON")
            yield conn
            conn.commit()
            try:
                after = conn.serialize()
            except sqlite3.OperationalError:
                after = b""  # Empty, uninitialised database only.
            if after != before:
                if read_only:
                    raise StorageUnavailable("會員端禁止修改資料。")
                # PostgreSQL commit must succeed before the caller sees success.
                remote.execute(
                    "UPDATE dali_private.database_images SET payload=%s, revision=revision+1, updated_at=now() WHERE sport=%s",
                    (after, sport),
                )
    except (ValueError, TypeError):
        raise
    except StorageUnavailable:
        raise
    except Exception:
        raise StorageUnavailable("永久資料交易未完成；請檢查連線或資料庫設定，未覆蓋已提交資料。") from None
    finally:
        conn.close()


def storage_label():
    return "PostgreSQL 永久保存（SQLite 相容儲存）" if os.environ.get("DATABASE_URL", "").strip() else "本機 SQLite：測試模式，重新部署可能遺失"
