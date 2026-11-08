import asyncio
from datetime import date, datetime, time, timedelta

import aiosqlite

from bot.i18n import LANG, _
from bot.utils import dt_to_str, str_to_dt

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    duration  INTEGER NOT NULL,
    price     INTEGER NOT NULL DEFAULT 0,
    active    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    service_id  INTEGER NOT NULL REFERENCES services(id),
    starts_at   TEXT    NOT NULL,
    ends_at     TEXT    NOT NULL,
    price       INTEGER NOT NULL,
    client_name TEXT    NOT NULL,
    phone       TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',
    reminded    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bookings_time ON bookings(status, starts_at);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id, status);
"""

_PRICES = (30, 80, 0) if LANG == "en" else (5000, 15000, 0)
DEFAULT_SERVICES = [
    (_("Стрижка"), 60, _PRICES[0]),
    (_("Окрашивание"), 120, _PRICES[1]),
    (_("Консультация"), 30, _PRICES[2]),
]

BOOKING_SELECT = """
SELECT b.*, s.name AS service_name
FROM bookings b JOIN services s ON s.id = b.service_id
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        # Одно соединение на весь бот: сериализуем записи, чтобы транзакции не перемешивались.
        self._lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() не вызван")
        return self._conn

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        if await self._fetchone("SELECT 1 FROM services LIMIT 1") is None:
            await self._conn.executemany(
                "INSERT INTO services (name, duration, price) VALUES (?, ?, ?)", DEFAULT_SERVICES
            )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _fetchone(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, params) as cur:
            return list(await cur.fetchall())

    async def _write(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        async with self._lock:
            return await self.conn.execute(sql, params)

    # --- Услуги ---

    async def list_services(self) -> list[aiosqlite.Row]:
        return await self._fetchall("SELECT * FROM services WHERE active = 1 ORDER BY id")

    async def get_service(self, service_id: int) -> aiosqlite.Row | None:
        return await self._fetchone("SELECT * FROM services WHERE id = ?", (service_id,))

    async def add_service(self, name: str, duration: int, price: int) -> int:
        cur = await self._write(
            "INSERT INTO services (name, duration, price) VALUES (?, ?, ?)", (name, duration, price)
        )
        return cur.lastrowid

    async def hide_service(self, service_id: int) -> bool:
        cur = await self._write("UPDATE services SET active = 0 WHERE id = ? AND active = 1", (service_id,))
        return cur.rowcount > 0

    # --- Записи ---

    async def busy_intervals(self, day: date) -> list[tuple[datetime, datetime]]:
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)
        rows = await self._fetchall(
            "SELECT starts_at, ends_at FROM bookings WHERE status = 'active' AND starts_at < ? AND ends_at > ?",
            (dt_to_str(end), dt_to_str(start)),
        )
        return [(str_to_dt(r["starts_at"]), str_to_dt(r["ends_at"])) for r in rows]

    async def create_booking(
        self,
        *,
        user_id: int,
        service_id: int,
        starts_at: datetime,
        ends_at: datetime,
        price: int,
        client_name: str,
        phone: str,
        reminded: bool,
    ) -> int | None:
        """Атомарно создаёт запись. None — если интервал уже пересекается с другой записью."""
        s, e = dt_to_str(starts_at), dt_to_str(ends_at)
        async with self._lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                clash = await self._fetchone(
                    "SELECT 1 FROM bookings WHERE status = 'active' AND starts_at < ? AND ends_at > ? LIMIT 1",
                    (e, s),
                )
                if clash:
                    await self.conn.execute("ROLLBACK")
                    return None
                cur = await self.conn.execute(
                    """INSERT INTO bookings
                       (user_id, service_id, starts_at, ends_at, price, client_name, phone, reminded)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, service_id, s, e, price, client_name, phone, int(reminded)),
                )
                await self.conn.execute("COMMIT")
                return cur.lastrowid
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise

    async def get_booking(self, booking_id: int) -> aiosqlite.Row | None:
        return await self._fetchone(f"{BOOKING_SELECT} WHERE b.id = ?", (booking_id,))

    async def user_bookings(self, user_id: int, now: datetime) -> list[aiosqlite.Row]:
        return await self._fetchall(
            f"{BOOKING_SELECT} WHERE b.user_id = ? AND b.status = 'active' AND b.starts_at > ? ORDER BY b.starts_at",
            (user_id, dt_to_str(now)),
        )

    async def count_user_active(self, user_id: int, now: datetime) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) FROM bookings WHERE user_id = ? AND status = 'active' AND starts_at > ?",
            (user_id, dt_to_str(now)),
        )
        return row[0]

    async def last_client(self, user_id: int) -> aiosqlite.Row | None:
        return await self._fetchone(
            "SELECT client_name, phone FROM bookings WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
        )

    async def cancel_booking(self, booking_id: int) -> bool:
        cur = await self._write(
            "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'", (booking_id,)
        )
        return cur.rowcount > 0

    async def bookings_on(self, day: date) -> list[aiosqlite.Row]:
        start = datetime.combine(day, time.min)
        return await self._fetchall(
            f"{BOOKING_SELECT} WHERE b.status = 'active' AND b.starts_at >= ? AND b.starts_at < ? ORDER BY b.starts_at",
            (dt_to_str(start), dt_to_str(start + timedelta(days=1))),
        )

    async def due_reminders(self, now: datetime, until: datetime) -> list[aiosqlite.Row]:
        return await self._fetchall(
            f"""{BOOKING_SELECT} WHERE b.status = 'active' AND b.reminded = 0
                AND b.starts_at > ? AND b.starts_at <= ?""",
            (dt_to_str(now), dt_to_str(until)),
        )

    async def mark_reminded(self, booking_id: int) -> None:
        await self._write("UPDATE bookings SET reminded = 1 WHERE id = ?", (booking_id,))
