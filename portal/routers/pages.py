from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.pesc.client import PescClient
from portal.infrastructure.config import settings
from portal.db import upsert_account, get_auto_submit, get_log
from portal.routers.meters import _get_auth

from datetime import datetime, timezone

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


def _datetimeformat(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    return dt.strftime("%d.%m.%Y %H:%M")


templates.env.filters["datetimeformat"] = _datetimeformat

_NAME_MAP = {
    "ГВС": "Горячее водоснабжение",
    "ХВС": "Холодное водоснабжение",
}

def _expand(name: str | None) -> str | None:
    if not name:
        return name
    for abbr, full in _NAME_MAP.items():
        name = name.replace(abbr, full)
    return name


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    async with _client() as c:
        bearer, account_ids = await _get_auth(c)
        accounts = []
        for account_id in account_ids:
            meters = await c.fetch_meters(bearer, account_id)
            upsert_account(account_id)
            for m in meters:
                m.name = _expand(m.name)
                for ind in m.indications:
                    ind.scale_name = _expand(ind.scale_name)
            accounts.append({
                "id": account_id,
                "meters": meters,
                "auto_submit": get_auto_submit(account_id),
            })

    return templates.TemplateResponse(request, "index.html", {"request": request, "accounts": accounts})


@router.get("/log", response_class=HTMLResponse)
async def log_page(request: Request) -> HTMLResponse:
    entries = get_log()
    return templates.TemplateResponse(request, "log.html", {"request": request, "entries": entries})


def _client() -> PescClient:
    return PescClient(
        totp_secret=settings.pesc_totp_secret,
        proxy_url=settings.pesc_proxy_url,
        auth_verification=settings.pesc_auth_verification,
    )
