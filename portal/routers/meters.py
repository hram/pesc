from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.pesc import PescClient
from portal.infrastructure.config import settings

router = APIRouter(prefix="/api", tags=["pesc"])


# ── Response schemas ──────────────────────────────────────────────────────────

class AccountInfoOut(BaseModel):
    account_id: str
    balance_text: str


class IndicationOut(BaseModel):
    meter_scale_id: int
    scale_name: str | None
    previous_reading: float | None
    previous_reading_date: str | None
    unit: str | None


class MeterOut(BaseModel):
    account_id: int
    registration: str
    name: str | None
    number_of_digits_right: int | None
    indications: list[IndicationOut]


class MeterReadingOut(BaseModel):
    meter: str
    kind: str
    value: float


class SubmitOut(BaseModel):
    info: AccountInfoOut | None
    readings: list[MeterReadingOut]


class ScaleValueIn(BaseModel):
    scale_id: int
    value: float


class MeterSubmitIn(BaseModel):
    account_id: int
    registration: str
    scales: list[ScaleValueIn]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/account", response_model=AccountInfoOut | None)
async def get_account() -> AccountInfoOut | None:
    """Return account balance from pesc.ru."""
    async with _client() as c:
        cookie = await c.fetch_session_cookie()
        bearer = await c.login(cookie, settings.pesc_login, settings.pesc_password)
        account_id = await c.fetch_first_account_id(cookie, bearer)
        info = await c.fetch_account_info(cookie, bearer, account_id)
    if info is None:
        return None
    return AccountInfoOut(account_id=info.account_id, balance_text=info.balance_text)


@router.get("/meters", response_model=list[MeterOut])
async def get_meters() -> list[MeterOut]:
    """Return meters for all accounts."""
    async with _client() as c:
        cookie = await c.fetch_session_cookie()
        bearer = await c.login(cookie, settings.pesc_login, settings.pesc_password)
        account_ids = await c.fetch_all_account_ids(cookie, bearer)
        result: list[MeterOut] = []
        for account_id in account_ids:
            meters = await c.fetch_meters(cookie, bearer, account_id)
            for m in meters:
                result.append(MeterOut(
                    account_id=account_id,
                    registration=m.registration,
                    name=m.name,
                    number_of_digits_right=m.number_of_digits_right,
                    indications=[
                        IndicationOut(
                            meter_scale_id=i.meter_scale_id,
                            scale_name=i.scale_name,
                            previous_reading=i.previous_reading,
                            previous_reading_date=i.previous_reading_date,
                            unit=i.unit,
                        )
                        for i in m.indications
                    ],
                ))
    return result


@router.post("/meters/submit", response_model=SubmitOut)
async def submit_readings() -> SubmitOut:
    """
    Submit readings for all meters (prev + min step) and verify the result.
    Returns the account info and the list of submitted values.
    """
    async with _client() as c:
        info, readings = await c.run(settings.pesc_login, settings.pesc_password)
    return SubmitOut(
        info=AccountInfoOut(account_id=info.account_id, balance_text=info.balance_text) if info else None,
        readings=[MeterReadingOut(meter=r.meter, kind=r.kind, value=r.value) for r in readings],
    )


@router.post("/meters/{account_id}/submit", response_model=SubmitOut)
async def submit_account(account_id: int) -> SubmitOut:
    """Submit prev+step readings for all meters of the given account."""
    async with _client() as c:
        cookie = await c.fetch_session_cookie()
        bearer = await c.login(cookie, settings.pesc_login, settings.pesc_password)
        info, readings = await c.run_for_account(cookie, bearer, account_id)
    return SubmitOut(
        info=AccountInfoOut(account_id=info.account_id, balance_text=info.balance_text) if info else None,
        readings=[MeterReadingOut(meter=r.meter, kind=r.kind, value=r.value) for r in readings],
    )


@router.post("/meters/submit-values", response_model=list[MeterReadingOut])
async def submit_values(body: list[MeterSubmitIn]) -> list[MeterReadingOut]:
    """Submit explicit meter values provided by the user."""
    async with _client() as c:
        cookie = await c.fetch_session_cookie()
        bearer = await c.login(cookie, settings.pesc_login, settings.pesc_password)
        results: list[MeterReadingOut] = []
        for item in body:
            payload = [{"scaleId": s.scale_id, "value": s.value} for s in item.scales]
            await c.submit_reading(cookie, bearer, item.account_id, item.registration, payload)
            for s in item.scales:
                results.append(MeterReadingOut(
                    meter=f"{item.registration}:{s.scale_id}",
                    kind=item.registration,
                    value=s.value,
                ))
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _client() -> PescClient:
    return PescClient(
        totp_secret=settings.pesc_totp_secret,
        proxy_url=settings.pesc_proxy_url,
        auth_verification=settings.pesc_auth_verification,
    )
