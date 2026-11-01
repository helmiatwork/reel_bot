"""Routine slots, autofill, Today feed and Telegram reminders."""
import datetime as _dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from .common import item_row

router = APIRouter()

DEFAULT_TZ = "Asia/Jakarta"
AUTOFILL_STATUSES = ("blueprint", "shoot", "edit", "review", "ready")
HORIZON_DAYS = 14
_OPEN = ("idea", "blueprint", "shoot", "edit", "review", "ready", "scheduled")


def next_slots(weekdays, post_time, tz, after, n, taken):
    """Next n aware slot datetimes strictly after `after` on `weekdays` (Monday = 0) at HH:MM in tz."""
    zone = ZoneInfo(tz)
    hh, mm = (int(x) for x in post_time.split(":"))
    day = after.astimezone(zone).date()
    out = []
    for _ in range(366):  # one year is plenty for any non-empty weekday set
        if len(out) >= n:
            break
        if day.weekday() in weekdays:
            slot = _dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=zone)
            if slot > after and slot not in taken:
                out.append(slot)
        day += _dt.timedelta(days=1)
    return out


def _when(v):
    if v is None:
        return None
    return v if isinstance(v, _dt.datetime) else _dt.datetime.fromisoformat(v)


def today_tasks(items, now):
    """What to do today. `now` must be aware and in the settings time zone (its date is "today")."""
    tasks = []
    for it in items:
        status = it.get("status") or it.get("stage")
        sched = _when(it.get("scheduled_at"))
        local = sched.astimezone(now.tzinfo) if sched else None
        action = None
        if status in ("idea", "blueprint", "shoot") and sched and sched <= now + _dt.timedelta(days=3):
            action = "shoot"
        elif status == "edit":
            action = "edit"
        elif status == "review":
            action = "evaluate"
        elif status in ("ready", "scheduled") and local and local.date() == now.date():
            action = "upload"
        if action:
            tasks.append({"item_id": it["id"], "title": it["title"], "action": action,
                          "scheduled_at": sched.isoformat() if sched else None})
    return tasks


def _conn():
    import main
    conn = main._db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="db unavailable")
    return conn


def _settings(cur) -> dict:
    cur.execute("SELECT weekdays, post_time, tz FROM routine_settings WHERE id = 1")
    row = cur.fetchone()
    return dict(zip(("weekdays", "post_time", "tz"), row)) if row else \
        {"weekdays": [0, 2, 4], "post_time": "19:00", "tz": DEFAULT_TZ}


@router.post("/schedule/autofill")
def autofill():
    import main
    conn = _conn()
    try:
        with conn.cursor() as cur:
            s = _settings(cur)
            now = _dt.datetime.now(_dt.timezone.utc)
            cur.execute("SELECT scheduled_at FROM content_items WHERE scheduled_at IS NOT NULL")
            taken = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT id FROM content_items WHERE stage = ANY(%s) AND scheduled_at IS NULL ORDER BY id",
                        (list(AUTOFILL_STATUSES),))
            ids = [r[0] for r in cur.fetchall()]
            slots = [x for x in next_slots(s["weekdays"], s["post_time"], s["tz"], now, len(ids), taken)
                     if x <= now + _dt.timedelta(days=HORIZON_DAYS)]
            assigned = []
            for item_id, slot in zip(ids, slots):
                cur.execute("UPDATE content_items SET scheduled_at = %s, "
                            "stage = CASE WHEN stage = 'ready' THEN 'scheduled' ELSE stage END, updated_at = now() "
                            "WHERE id = %s AND scheduled_at IS NULL RETURNING id", (slot, item_id))
                if cur.fetchone():
                    assigned.append({"item_id": item_id, "scheduled_at": slot.isoformat()})
        conn.commit()
        return main._json({"assigned": assigned})
    finally:
        conn.close()


@router.get("/today")
def today():
    import main
    conn = _conn()
    try:
        with conn.cursor() as cur:
            s = _settings(cur)
            now = _dt.datetime.now(ZoneInfo(s["tz"]))
            cur.execute("SELECT * FROM content_items WHERE stage = ANY(%s) ORDER BY scheduled_at NULLS LAST, id",
                        (list(_OPEN),))
            items = [item_row(cur.description, r) for r in cur.fetchall()]
            cur.execute("SELECT m.content_item_id, c.title, m.url, m.checkpoint_h, m.views, m.likes, m.comments, "
                        "m.captured_at FROM monitor_snapshots m JOIN content_items c ON c.id = m.content_item_id "
                        "WHERE m.alerted ORDER BY m.captured_at DESC LIMIT 10")
            alerts = [item_row(cur.description, r) for r in cur.fetchall()]
        horizon = now + _dt.timedelta(days=7)
        upcoming = [i for i in items if i["scheduled_at"] and now <= _when(i["scheduled_at"]) <= horizon]
        return main._json({"tasks": today_tasks(items, now), "alerts": alerts, "upcoming": upcoming})
    finally:
        conn.close()


def send_reminders(now) -> int:
    """H-1 and day-of Telegram reminders. Each reminder is claimed in the DB before sending, so a
    second run (or an overlapping tick) sends nothing; a failed send releases the claim for retry."""
    import main
    conn = main._db_conn()
    if not conn:
        return 0
    sent = 0
    try:
        with conn.cursor() as cur:
            tz = ZoneInfo(_settings(cur)["tz"])
            local = now.astimezone(tz)
            day0 = local.replace(hour=0, minute=0, second=0, microsecond=0)
            kinds = (
                ("reminded_d1_at", "H-1", now + _dt.timedelta(hours=20), now + _dt.timedelta(hours=28)),
                ("reminded_d0_at", "Hari ini", day0, day0 + _dt.timedelta(days=1)),
            )
            for col, label, lo, hi in kinds:  # col comes from the literal tuple above, never user input
                cur.execute(f"SELECT id, title, scheduled_at FROM content_items WHERE {col} IS NULL "
                            "AND scheduled_at >= %s AND scheduled_at < %s AND stage = ANY(%s)",
                            (lo, hi, list(_OPEN)))
                for item_id, title, sched in cur.fetchall():
                    cur.execute(f"UPDATE content_items SET {col} = now() WHERE id = %s AND {col} IS NULL "
                                "RETURNING id", (item_id,))
                    if not cur.fetchone():
                        continue
                    conn.commit()
                    text = f"{label}: '{title}' tayang {sched.astimezone(tz):%d %b %H:%M} ({tz.key})."
                    if main._telegram_notify(text):
                        sent += 1
                    else:
                        cur.execute(f"UPDATE content_items SET {col} = NULL WHERE id = %s", (item_id,))
                        conn.commit()
        return sent
    finally:
        conn.close()
