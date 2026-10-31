"""POST /atm/cron/tick: called every 15 minutes by launchd. Each job is isolated."""
import datetime as _dt

from fastapi import APIRouter, Depends, Header

from . import monitor, schedule

router = APIRouter()


def _admin(x_api_key: str = Header(None)) -> None:
    import main
    main.verify_admin_key(x_api_key)


def _safe(name, fn, default, errors):
    try:
        return fn()
    except Exception as exc:
        print(f"[atm] tick job '{name}' failed: {exc}")
        errors.append(name)
        return default


@router.post("/cron/tick")
def tick(_: None = Depends(_admin)):
    now = _dt.datetime.now(_dt.timezone.utc)
    errors: list = []
    return {"reminders": _safe("reminders", lambda: schedule.send_reminders(now), 0, errors),
            "monitor": _safe("monitor", lambda: monitor.run_monitor(now), {}, errors),
            "post_evals": 0, "errors": errors}
