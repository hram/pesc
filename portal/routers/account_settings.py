from fastapi import APIRouter
from pydantic import BaseModel

from portal.db import get_auto_submit, set_auto_submit
from portal.scheduler import run_auto_submit

router = APIRouter(prefix="/api/accounts", tags=["settings"])


class AccountSettingsOut(BaseModel):
    account_id: int
    auto_submit: bool


class AccountSettingsPatch(BaseModel):
    auto_submit: bool


@router.get("/{account_id}/settings", response_model=AccountSettingsOut)
async def get_settings(account_id: int) -> AccountSettingsOut:
    return AccountSettingsOut(
        account_id=account_id,
        auto_submit=get_auto_submit(account_id),
    )


@router.patch("/{account_id}/settings", response_model=AccountSettingsOut)
async def update_settings(account_id: int, body: AccountSettingsPatch) -> AccountSettingsOut:
    set_auto_submit(account_id, body.auto_submit)
    return AccountSettingsOut(account_id=account_id, auto_submit=body.auto_submit)


@router.post("/trigger", status_code=204)
async def trigger_scheduler() -> None:
    """Запустить автоподачу вручную (для проверки планировщика)."""
    await run_auto_submit()
