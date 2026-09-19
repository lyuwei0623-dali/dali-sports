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
import threading


class StorageUnavailable(RuntimeError):
    pass


# Streamlit reruns the script whenever an administrator changes a widget.  The
# first durable implementation fetched and re-uploaded the complete SQLite
# image on every one of those reruns.  Keep a process-local copy keyed by the
# remote revision instead: PostgreSQL remains authoritative, but ordinary
# reads only transfer a tiny revision number after the first load.
_image_cache: dict[tuple[str, str], tuple[int, bytes]] = {}
_cache_lock = threading.RLock()


def _cache_key(sport: str) -> tuple[str, str]:
    return (os.environ.get("DATABASE_URL", ""), sport)


def _cached_image(sport: str, revision: int) -> bytes | None:
    with _cache_lock:
        cached = _image_cache.get(_cache_key(sport))
        return cached[1] if cached and cached[0] == revision else None


def _remember_image(sport: str, revision: int, payload: bytes) -> None:
    with _cache_lock:
        _image_cache[_cache_key(sport)] = (revision, payload)


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
            # Acquire a row lock only for an operation that may write.  The
            # member path is deliberately a small revision read plus local
            # SQLite SELECTs; it never obtains a write lock.
            revision_row = remote.execute(
                "SELECT revision FROM dali_private.database_images WHERE sport=%s" + ("" if read_only else " FOR UPDATE"),
                (sport,),
            ).fetchone()
            if revision_row is None:
                raise StorageUnavailable("永久資料庫尚未初始化；請執行 database_setup.sql。")
            revision = int(revision_row[0])
            before = _cached_image(sport, revision)
            if before is None:
                payload_row = remote.execute(
                    "SELECT payload FROM dali_private.database_images WHERE sport=%s", (sport,)
                ).fetchone()
                before = bytes(payload_row[0]) if payload_row and payload_row[0] else b""
                _remember_image(sport, revision, before)
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
                _remember_image(sport, revision + 1, after)
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
