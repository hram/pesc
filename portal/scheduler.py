import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from portal.db import get_auto_submit_accounts, add_log_entry
from portal.infrastructure.config import settings
from portal.schedule import should_submit
from src.pesc.client import PescClient

log = logging.getLogger(__name__)

MOSCOW_TZ = timezone.utc  # APScheduler уже запускает задачу по МСК


async def run_auto_submit(*, force: bool = False) -> None:
    import zoneinfo
    moscow_today = datetime.now(tz=zoneinfo.ZoneInfo("Europe/Moscow")).date()
    allowed, reason = should_submit(moscow_today)
    if not allowed:
        if force:
            log.info("auto_submit: force=true, игнорируем ограничение (%s)", reason)
        else:
            log.info("auto_submit: пропуск — %s", reason)
            return

    account_ids = get_auto_submit_accounts()
    if not account_ids:
        log.info("auto_submit: нет счетов с включённой автоподачей")
        return

    log.info("auto_submit: запуск для счетов %s (%s)", account_ids, reason)

    async with PescClient(
        totp_secret=settings.pesc_totp_secret,
        proxy_url=settings.pesc_proxy_url,
        auth_verification=settings.pesc_auth_verification,
    ) as client:
        cookie = await client.fetch_session_cookie()
        bearer = await client.login(cookie, settings.pesc_login, settings.pesc_password)

        for account_id in account_ids:
            try:
                info, readings = await client.run_for_account(cookie, bearer, account_id)
                log.info(
                    "auto_submit: account %s — %d reading(s) submitted. %s",
                    account_id, len(readings), info.balance_text if info else "",
                )
                add_log_entry(account_id, success=True, readings_count=len(readings))
            except Exception as exc:
                log.error("auto_submit: account %s failed: %s", account_id, exc)
                add_log_entry(account_id, success=False, error=str(exc))


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        run_auto_submit,
        trigger="cron",
        hour=settings.scheduler_hour,
        minute=settings.scheduler_minute,
        id="auto_submit",
        replace_existing=True,
    )
    return scheduler
