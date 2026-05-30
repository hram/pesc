import os
os.environ.setdefault("PESC_LOGIN", "x")
os.environ.setdefault("PESC_PASSWORD", "x")

from portal.main import app  # noqa: F401
from portal.routers.pages import router as pages_router  # noqa: F401
from portal.routers.meters import router as meters_router  # noqa: F401
from src.pesc.client import PescClient  # noqa: F401
