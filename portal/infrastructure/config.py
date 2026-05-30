import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is required but not set")
    return value


class Settings:
    pesc_login: str = _require("PESC_LOGIN")
    pesc_password: str = _require("PESC_PASSWORD")
    pesc_auth_verification: str | None = os.environ.get("PESC_AUTH_VERIFICATION") or None
    pesc_totp_secret: str | None = os.environ.get("PESC_TOTP_SECRET") or None
    pesc_proxy_url: str | None = os.environ.get("PESC_PROXY_URL") or None
    data_dir: str = os.environ.get("DATA_DIR") or "data"
    # Time to run auto-submit daily (Moscow time)
    scheduler_hour: int = int(os.environ.get("SCHEDULER_HOUR") or 12)
    scheduler_minute: int = int(os.environ.get("SCHEDULER_MINUTE") or 0)


settings = Settings()
