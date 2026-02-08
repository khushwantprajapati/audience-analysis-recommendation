"""Meta OAuth: login redirect and callback."""
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Account
from app.utils.crypto import encrypt_token

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

META_OAUTH_URL = "https://www.facebook.com/v18.0/dialog/oauth"
META_TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"
META_GRAPH_ME = "https://graph.facebook.com/v18.0/me"
META_GRAPH_ACCOUNTS = "https://graph.facebook.com/v18.0/me/adaccounts"
SCOPES = "ads_read,ads_management"


@router.get("/meta/login")
def meta_login():
    """Redirect user to Meta OAuth consent."""
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise HTTPException(
            status_code=503,
            detail="Meta app credentials not configured. Set META_APP_ID and META_APP_SECRET.",
        )
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.meta_redirect_uri,
        "scope": SCOPES,
        "response_type": "code",
    }
    url = f"{META_OAUTH_URL}?{urlencode(params)}"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=url)


@router.get("/meta/callback")
async def meta_callback(code: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    """Exchange code for access token, get long-lived token, store account."""
    if error:
        raise HTTPException(status_code=400, detail=f"Meta OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    async with httpx.AsyncClient() as client:
        # Exchange code for short-lived token
        r = await client.get(
            META_TOKEN_URL,
            params={
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "redirect_uri": settings.meta_redirect_uri,
                "code": code,
            },
        )
        r.raise_for_status()
        data = r.json()
        access_token = data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No access_token in response")

        # Exchange for long-lived token (60 days)
        r2 = await client.get(
            META_TOKEN_URL,
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "fb_exchange_token": access_token,
            },
        )
        r2.raise_for_status()
        data2 = r2.json()
        long_lived_token = data2.get("access_token", access_token)
        expires_in = data2.get("expires_in")  # seconds

        # Get user id (optional, for display)
        me = await client.get(
            META_GRAPH_ME,
            params={"access_token": long_lived_token, "fields": "id,name"},
        )
        me.raise_for_status()
        me_data = me.json()

        # Get first ad account as default
        accs = await client.get(
            META_GRAPH_ACCOUNTS,
            params={
                "access_token": long_lived_token,
                "fields": "id,name,account_id",
            },
        )
        accs.raise_for_status()
        accs_data = accs.json()
        ad_accounts = accs_data.get("data", [])
        if not ad_accounts:
            raise HTTPException(
                status_code=400,
                detail="No ad accounts found for this user. Ensure ads_read and ads_management are granted.",
            )
    # End httpx

    from datetime import datetime, timezone, timedelta
    token_expires_at = None
    if expires_in:
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    encrypted_token = encrypt_token(long_lived_token)

    # Store ALL ad accounts, not just the first
    for ad_account in ad_accounts:
        meta_account_id = ad_account.get("account_id") or ad_account.get("id", "")
        if not meta_account_id:
            continue
        # Strip "act_" prefix if present in account_id
        meta_account_id = meta_account_id.replace("act_", "")
        account_name = ad_account.get("name") or f"Account {meta_account_id}"

        existing = db.query(Account).filter(Account.meta_account_id == meta_account_id).first()
        if existing:
            existing.access_token = encrypted_token
            existing.token_expires_at = token_expires_at
            existing.account_name = account_name
        else:
            account = Account(
                id=str(uuid.uuid4()),
                meta_account_id=meta_account_id,
                account_name=account_name,
                access_token=encrypted_token,
                token_expires_at=token_expires_at,
            )
            db.add(account)
    db.commit()

    from fastapi.responses import RedirectResponse
    frontend = settings.frontend_url.rstrip("/")
    return RedirectResponse(url=f"{frontend}/dashboard")
