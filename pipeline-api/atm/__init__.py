from fastapi import APIRouter

from . import blueprint, items, voice

router = APIRouter(prefix="/atm")
router.include_router(items.router)
router.include_router(blueprint.router)
router.include_router(voice.router)
