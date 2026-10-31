from fastapi import APIRouter

from . import blueprint, cron, evaluate, items, monitor, schedule, voice

router = APIRouter(prefix="/atm")
router.include_router(items.router)
router.include_router(blueprint.router)
router.include_router(voice.router)
router.include_router(schedule.router)
router.include_router(cron.router)
router.include_router(evaluate.router)
router.include_router(monitor.router)
