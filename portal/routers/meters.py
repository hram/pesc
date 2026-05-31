import asyncio
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.pesc import PescClient
from src.pesc.client import PescAuthError
from portal.infrastructure.config import settings

router = APIRouter(prefix="/api", tags=["pesc"])

# ── Auth cache ────────────────────────────────────────────────────────────────
_auth_cache: dict = {}
_auth_lock = asyncio.Lock()


async def _get_auth(c: PescClient) -> tuple[str, list[int]]:
    """Return (bearer, account_ids). Authenticates only when cache is empty."""
    async with _auth_lock:
        if "bearer" in _auth_cache:
            return _auth_cache["bearer"], _auth_cache["account_ids"]
        bearer = await c.login(settings.pesc_login, settings.pesc_password)
        account_ids = await c.fetch_all_account_ids(bearer)
        _auth_cache["bearer"] = bearer
        _auth_cache["account_ids"] = account_ids
        return bearer, account_ids


async def _call(c: PescClient, fn):
    """Run fn(bearer, account_ids), retrying once if the token was rejected."""
    for attempt in range(2):
        bearer, account_ids = await _get_auth(c)
        try:
            return await fn(bearer, account_ids)
        except PescAuthError:
            if attempt == 1:
                raise
            _auth_cache.clear()


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
    async with _client() as c:
        async def fetch(bearer, account_ids):
            return await c.fetch_account_info(bearer, account_ids[0])
        info = await _call(c, fetch)
    if info is None:
        return None
    return AccountInfoOut(account_id=info.account_id, balance_text=info.balance_text)


@router.get("/meters", response_model=list[MeterOut])
async def get_meters() -> list[MeterOut]:
    async with _client() as c:
        async def fetch(bearer, account_ids):
            return await asyncio.gather(*[c.fetch_meters(bearer, aid) for aid in account_ids])
        meters_lists = await _call(c, fetch)
    bearer, account_ids = _auth_cache["bearer"], _auth_cache["account_ids"]
    result: list[MeterOut] = []
    for account_id, meters in zip(account_ids, meters_lists):
        for m in meters:
            result.append(MeterOut(account_id=account_id, registration=m.registration, name=m.name,
                number_of_digits_right=m.number_of_digits_right,
                indications=[IndicationOut(meter_scale_id=i.meter_scale_id, scale_name=i.scale_name,
                    previous_reading=i.previous_reading, previous_reading_date=i.previous_reading_date,
                    unit=i.unit) for i in m.indications]))
    return result


@router.get("/dashboard")
async def get_dashboard() -> dict:
    """Account info + all meters; uses cached auth. Used by the meters aggregator portal."""
    async with _client() as c:
        async def fetch(bearer, account_ids):
            return await asyncio.gather(
                c.fetch_account_info(bearer, account_ids[0]),
                *[c.fetch_meters(bearer, aid) for aid in account_ids],
            )
        results = await _call(c, fetch)
    account_ids = _auth_cache["account_ids"]
    info, *meters_lists = results
    meters = []
    for account_id, meter_list in zip(account_ids, meters_lists):
        for m in meter_list:
            meters.append(MeterOut(account_id=account_id, registration=m.registration, name=m.name,
                number_of_digits_right=m.number_of_digits_right,
                indications=[IndicationOut(meter_scale_id=i.meter_scale_id, scale_name=i.scale_name,
                    previous_reading=i.previous_reading, previous_reading_date=i.previous_reading_date,
                    unit=i.unit) for i in m.indications]))
    return {
        "account": AccountInfoOut(account_id=info.account_id, balance_text=info.balance_text) if info else None,
        "meters": meters,
    }


@router.post("/meters/{account_id}/submit", response_model=SubmitOut)
async def submit_account(account_id: int) -> SubmitOut:
    async with _client() as c:
        async def fetch(bearer, _account_ids):
            return await c.run_for_account(bearer, account_id)
        info, readings = await _call(c, fetch)
    _auth_cache.clear()
    return SubmitOut(
        info=AccountInfoOut(account_id=info.account_id, balance_text=info.balance_text) if info else None,
        readings=[MeterReadingOut(meter=r.meter, kind=r.kind, value=r.value) for r in readings],
    )


@router.post("/meters/submit-values", response_model=list[MeterReadingOut])
async def submit_values(body: list[MeterSubmitIn]) -> list[MeterReadingOut]:
    async with _client() as c:
        async def fetch(bearer, _account_ids):
            results: list[MeterReadingOut] = []
            for item in body:
                payload = [{"scaleId": s.scale_id, "value": s.value} for s in item.scales]
                await c.submit_reading(bearer, item.account_id, item.registration, payload)
                for s in item.scales:
                    results.append(MeterReadingOut(meter=f"{item.registration}:{s.scale_id}",
                        kind=item.registration, value=s.value))
            return results
        results = await _call(c, fetch)
    _auth_cache.clear()
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _client() -> PescClient:
    return PescClient(
        totp_secret=settings.pesc_totp_secret,
        proxy_url=settings.pesc_proxy_url,
        auth_verification=settings.pesc_auth_verification,
    )
