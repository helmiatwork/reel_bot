from fastapi import APIRouter

from . import blueprint, items

router = APIRouter(prefix="/atm")
router.include_router(items.router)
router.include_router(blueprint.router)
