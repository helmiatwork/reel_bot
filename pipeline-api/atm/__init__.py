from fastapi import APIRouter

from . import blueprint, cron, evaluate, items, learn, mine, monitor, package, schedule, voice

router = APIRouter(prefix="/atm")
router.include_router(items.router)
router.include_router(blueprint.router)
router.include_router(voice.router)
router.include_router(schedule.router)
router.include_router(cron.router)
router.include_router(evaluate.router)
router.include_router(monitor.router)
router.include_router(learn.router)
router.include_router(mine.router)
router.include_router(package.router)
