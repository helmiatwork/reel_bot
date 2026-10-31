from fastapi import APIRouter

from . import items

router = APIRouter(prefix="/atm")
router.include_router(items.router)
