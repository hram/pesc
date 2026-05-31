"""Async HTTP client for ikus.pesc.ru."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx

from .models import AccountInfo, IndicationScale, Meter, MeterReading
from .totp import generate_totp

class PescAuthError(RuntimeError):
    """Server returned 401/403 — token expired or invalid."""


BASE = "https://ikus.pesc.ru"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36"
)
CUSTOMER = "ikus-spb"
VERIFY_DELAY_S = 1.5
INTEGER_INCREMENT = 1
DEFAULT_DECIMALS = 3


class PescClient:
    def __init__(
        self,
        *,
        totp_secret: str | None = None,
        proxy_url: str | None = None,
        auth_verification: str | None = None,
    ) -> None:
        self._totp_secret = totp_secret or None
        self._auth_verification = auth_verification or None
        kwargs: dict[str, Any] = {}
        if proxy_url:
            kwargs["proxy"] = proxy_url
        self._http = httpx.AsyncClient(**kwargs)

    async def __aenter__(self) -> "PescClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._http.aclose()

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def login(self, username: str, password: str) -> str:
        """Authenticate and return a Bearer token. Handles TOTP 2FA automatically."""
        res = await self._http.post(
            f"{BASE}/api/v8/users/auth",
            headers={
                **self._headers(),
                "content-type": "application/json",
                "withtotp": "true",
                "captcha": "none",
                **({"auth-verification": self._auth_verification} if self._auth_verification else {}),
            },
            content=_dump({"type": "PHONE", "login": username, "password": password}),
        )
        text = res.text

        if res.status_code == 424:
            data = _try_load(text) or {}
            tx_id: str | None = data.get("transactionId")
            types: list[str] = data.get("types") or []
            if tx_id is None:
                raise RuntimeError(f"2FA required but transactionId missing: {text[:200]}")
            if "TOTP" not in types:
                raise RuntimeError(
                    f"2FA required on pesc.ru (types={','.join(types)}). "
                    "Only TOTP is supported; enable TOTP in account settings."
                )
            if not self._totp_secret:
                raise RuntimeError("2FA required on pesc.ru but totp_secret is not configured.")
            return await self._solve_totp(tx_id)

        _raise(res, "POST /v8/users/auth")
        auth: str | None = _load(text).get("auth")
        if not auth:
            raise RuntimeError('POST /v8/users/auth: response missing "auth" token')
        return auth

    async def _solve_totp(self, transaction_id: str) -> str:
        import time
        assert self._totp_secret is not None
        code = generate_totp(self._totp_secret, int(time.time() * 1000))
        path = f"/api/v1/dfa/{transaction_id}/totp/verify"
        res = await self._http.post(
            f"{BASE}{path}",
            headers={**self._headers(), "content-type": "application/json"},
            content=_dump({"code": code}),
        )
        _raise(res, f"POST {path}")
        auth: str | None = _load(res.text).get("auth")
        if not auth:
            raise RuntimeError(f'POST {path}: response missing "auth" token')
        return auth

    # ── Account ───────────────────────────────────────────────────────────────

    async def fetch_first_account_id(self, bearer: str) -> int:
        ids = await self.fetch_all_account_ids(bearer)
        return ids[0]

    async def fetch_all_account_ids(self, bearer: str, *, skip_archived: bool = True) -> list[int]:
        groups: list[dict[str, Any]] = await self._get("/api/v6/accounts/groups", bearer)
        ids: list[int] = []
        for g in groups:
            if skip_archived and "архив" in (g.get("name") or "").lower():
                continue
            ids.extend(g.get("accounts") or [])
        if not ids:
            raise RuntimeError("No accounts found in any group on pesc.ru")
        return ids

    async def fetch_account_info(self, bearer: str, account_id: int) -> AccountInfo | None:
        path = f"/api/v7/accounts/{account_id}/payments/at/current/amount/discretion"
        try:
            items: list[dict[str, Any]] = await self._get(path, bearer)
        except Exception:
            return None
        if not isinstance(items, list):
            items = [items]
        total: float = sum(
            (item.get("charge") or {}).get("balance", {}).get("value", 0)
            + (item.get("fine") or {}).get("balance", {}).get("value", 0)
            for item in items
        )
        if total < 0:
            balance_text = f"переплата {abs(total):.2f} руб"
        elif total > 0:
            balance_text = f"задолженность {total:.2f} руб"
        else:
            balance_text = "расчёты без долга"
        return AccountInfo(account_id=str(account_id), balance_text=balance_text)

    # ── Meters ────────────────────────────────────────────────────────────────

    async def fetch_meters(self, bearer: str, account_id: int) -> list[Meter]:
        raw: list[dict[str, Any]] = await self._get(
            f"/api/v6/accounts/{account_id}/meters/info", bearer
        )
        return [_parse_meter(m) for m in raw]

    async def submit_reading(
        self,
        bearer: str,
        account_id: int,
        registration: str,
        payload: list[dict[str, Any]],
    ) -> None:
        path = f"/api/v8/accounts/{account_id}/meters/{registration}/reading"
        res = await self._http.post(
            f"{BASE}{path}",
            headers={**self._headers(bearer), "content-type": "application/json"},
            content=_dump(payload),
        )
        _raise(res, f"POST {path}")

    # ── High-level ────────────────────────────────────────────────────────────

    async def run(
        self,
        username: str,
        password: str,
        *,
        last_value_for: Callable[[str], float | None] | None = None,
    ) -> tuple[AccountInfo | None, list[MeterReading]]:
        bearer = await self.login(username, password)
        account_id = await self.fetch_first_account_id(bearer)
        return await self.run_for_account(bearer, account_id)

    async def run_for_account(
        self,
        bearer: str,
        account_id: int,
    ) -> tuple[AccountInfo | None, list[MeterReading]]:
        """Fetch meters for account_id, submit the same values as received, verify."""
        info = await self.fetch_account_info(bearer, account_id)
        meters = await self.fetch_meters(bearer, account_id)

        submitted: list[MeterReading] = []

        for meter in meters:
            if not meter.indications:
                continue
            payload: list[dict[str, Any]] = []
            for ind in meter.indications:
                key = f"{meter.registration}:{ind.meter_scale_id}"
                if ind.previous_reading is None:
                    raise RuntimeError(f"Meter {key}: no previous reading on portal, cannot submit")
                payload.append({"scaleId": ind.meter_scale_id, "value": ind.previous_reading})
                submitted.append(MeterReading(
                    meter=key,
                    kind=ind.scale_name or meter.name or "unknown",
                    value=ind.previous_reading,
                ))
            await self.submit_reading(bearer, account_id, meter.registration, payload)

        if submitted:
            await asyncio.sleep(VERIFY_DELAY_S)
            after = await self.fetch_meters(bearer, account_id)
            for reading in submitted:
                reg, scale_str = reading.meter.split(":", 1)
                scale_id = int(scale_str)
                m = next((x for x in after if x.registration == reg), None)
                ind = next((i for i in (m.indications if m else []) if i.meter_scale_id == scale_id), None)
                if ind is None:
                    raise RuntimeError(f"Meter {reading.meter} disappeared after submit")
                actual = ind.previous_reading or 0.0
                if abs(actual - reading.value) > 0.0001:
                    raise RuntimeError(
                        f"Meter {reading.meter}: previousReading after submit is {actual}, "
                        f"expected {reading.value}"
                    )

        return info, submitted

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _headers(self, bearer: str | None = None) -> dict[str, str]:
        h: dict[str, str] = {
            "user-agent": UA,
            "accept": "application/json, text/plain, */*",
            "customer": CUSTOMER,
        }
        if bearer:
            h["authorization"] = f"Bearer {bearer}"
        return h

    async def _get(self, path: str, bearer: str) -> Any:
        res = await self._http.get(f"{BASE}{path}", headers=self._headers(bearer))
        _raise(res, f"GET {path}")
        return _load(res.text)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _raise(res: httpx.Response, label: str) -> None:
    if res.status_code in (401, 403):
        raise PescAuthError(f"{label} → HTTP {res.status_code}")
    if not res.is_success:
        raise RuntimeError(f"{label} → HTTP {res.status_code}: {res.text[:200]}")


def _dump(obj: Any) -> bytes:
    return json.dumps(obj).encode()


def _load(text: str) -> dict[str, Any]:
    return json.loads(text)


def _try_load(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _round(n: float, decimals: int) -> float:
    factor = 10 ** decimals
    return round(n * factor) / factor


def _parse_meter(raw: dict[str, Any]) -> Meter:
    indications = [
        IndicationScale(
            meter_scale_id=i["meterScaleId"],
            scale_name=i.get("scaleName"),
            previous_reading=i.get("previousReading"),
            previous_reading_date=i.get("previousReadingDate"),
            unit=i.get("unit"),
        )
        for i in raw.get("indications") or []
    ]
    return Meter(
        registration=raw["id"]["registration"],
        name=raw.get("name"),
        subservice_id=raw.get("subserviceId"),
        number_of_digits_right=raw.get("numberOfDigitsRight"),
        indications=indications,
    )
