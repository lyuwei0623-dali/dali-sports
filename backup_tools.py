"""Admin-only export and non-overwriting import of persistent database images."""
import io
import sqlite3
import zipfile
from durable_store import _remote_connect, StorageUnavailable


def export_backup(app):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        with app.mlb_store._connect() as conn:
            archive.writestr("mlb.sqlite3", conn.serialize())
        with app.football._db() as conn:
            archive.writestr("football.sqlite3", conn.serialize())
    return buffer.getvalue()


def _validate_image(payload, sport):
    if not payload.startswith(b"SQLite format 3\x00"):
        raise ValueError("不是 SQLite 備份")
    conn = sqlite3.connect(":memory:")
    try:
        conn.deserialize(payload)
        conn.execute("PRAGMA trusted_schema=OFF")
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("備份完整性檢查失敗")
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = "mlb_automatic_snapshots" if sport == "mlb" else "football_automatic_snapshots"
        if required not in names:
            raise ValueError("備份運動種類不符")
        # All imported objects must belong to this app's sport namespace.
        objects = conn.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if any(not (row[0].startswith(sport + "_") or (sport == "mlb" and row[0].startswith("idx_mlb_"))) for row in objects):
            raise ValueError("備份包含不支援的資料表或物件")
        count = sum(conn.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                    for name in names if not name.startswith("sqlite_"))
        return count
    finally:
        conn.close()


def import_into_empty_database(data):
    """Explicit admin action. Reject existing data; never overwrite a live DB."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sorted(archive.namelist()) != ["football.sqlite3", "mlb.sqlite3"]:
            raise ValueError("只接受此 APP 匯出的雙資料庫備份")
        if any(info.file_size > 50 * 1024 * 1024 for info in archive.infolist()):
            raise ValueError("備份超過 50 MiB 限制，請使用管理員離線遷移")
        payloads = {sport: archive.read(sport + ".sqlite3") for sport in ("mlb", "football")}
    for sport, payload in payloads.items():
        _validate_image(payload, sport)
    try:
        with _remote_connect() as remote:
            remote.execute("SET LOCAL lock_timeout = '15s'")
            for sport in ("mlb", "football"):
                row = remote.execute("SELECT payload FROM dali_private.database_images WHERE sport=%s FOR UPDATE", (sport,)).fetchone()
                if row is None:
                    raise ValueError("請先執行 database_setup.sql")
                if row[0] and _validate_image(bytes(row[0]), sport):
                    raise ValueError("永久資料庫已有紀錄；禁止覆蓋，請另建空白資料庫進行復原")
            for sport, payload in payloads.items():
                remote.execute("UPDATE dali_private.database_images SET payload=%s,revision=revision+1,updated_at=now() WHERE sport=%s", (payload,sport))
    except ValueError:
        raise
    except Exception:
        raise StorageUnavailable("備份匯入未完成，原資料未被覆蓋。") from None
