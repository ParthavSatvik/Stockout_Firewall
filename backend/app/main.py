import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import get_settings
from app.routers import (
    admin,
    allocations,
    auth,
    catalog,
    continuity,
    integrations,
    intelligence,
    orders,
    payments,
    products,
    reconciliation,
    scenarios,
    suppliers,
)

settings = get_settings()
logging.basicConfig(level=settings.log_level)

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

app = FastAPI(title="Stockout Firewall API", version="0.1.0")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(catalog.router)
app.include_router(suppliers.router)
app.include_router(orders.router)
app.include_router(allocations.router)
# Before payments: its GET /api/payments/{payment_id} would otherwise capture /api/payments/config.
app.include_router(integrations.router)
app.include_router(payments.router)
app.include_router(reconciliation.router)
app.include_router(scenarios.router)
app.include_router(admin.router)
app.include_router(continuity.router)


@app.middleware("http")
async def send_queued_messages(request, call_next):
    """WhatsApp messages queued by the request are sent after the response is returned."""
    response = await call_next(request)
    if request.method != "GET" and response.background is None:
        from starlette.background import BackgroundTask

        from app.services.notify import dispatch_queued
        response.background = BackgroundTask(dispatch_queued)
    return response
app.include_router(intelligence.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "demo_mode": settings.demo_mode,
        "sarvam_configured": settings.sarvam_configured,
        "paytm_configured": settings.paytm_configured,
        "google_maps_configured": settings.google_maps_configured,
        "supabase_configured": settings.supabase_configured,
    }
