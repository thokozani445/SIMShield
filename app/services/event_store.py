import aiosqlite
from datetime import datetime, timezone
from app.models import EventRecord, RiskAction

DB_PATH = "simshield.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    request_id    TEXT PRIMARY KEY,
    msisdn_masked TEXT NOT NULL,
    action        TEXT NOT NULL,
    risk_score    INTEGER NOT NULL,
    agent_invoked INTEGER NOT NULL DEFAULT 0,
    timestamp     TEXT NOT NULL
)
"""


class EventStore:
    """
    Append-only event log. Every risk check is written here.
    Records are never updated or deleted — this is the audit trail.
    """

    async def init(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(CREATE_SQL)
            await db.commit()

    async def append(self, event: EventRecord) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO events
                   (request_id, msisdn_masked, action, risk_score, agent_invoked, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.request_id,
                    event.msisdn_masked,
                    event.action.value,
                    event.risk_score,
                    1 if event.agent_invoked else 0,
                    event.timestamp.isoformat(),
                ),
            )
            await db.commit()

    async def get_recent(
        self, limit: int = 20, since: str | None = None
    ) -> list[EventRecord]:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if since:
                cur = await db.execute(
                    "SELECT * FROM events WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
                    (since, limit),
                )
            else:
                cur = await db.execute(
                    "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            rows = await cur.fetchall()

        return [
            EventRecord(
                request_id=row["request_id"],
                msisdn_masked=row["msisdn_masked"],
                action=RiskAction(row["action"]),
                risk_score=row["risk_score"],
                agent_invoked=bool(row["agent_invoked"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )
            for row in rows
        ]