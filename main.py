import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, init_db, User, GlobalStats, apply_boost


app = FastAPI(title="Telegram Clicker API")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALLOWED_ORIGINS = ["https://github.com", "https://<username>.github.io", "https://abc123.ngrok.io"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StarsInvoiceRequest(BaseModel):
    user_id: int
    booster_type: str

class ClickRequest(BaseModel):
    init_data: str


class ClickResponse(BaseModel):
    success: bool
    user_id: int
    new_click_count: int


class StatsResponse(BaseModel):
    user_clicks: int
    global_clicks: int


def validate_telegram_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """Валидация initData Telegram WebApp с использованием HMAC-SHA256"""
    try:
        params = {}
        for pair in init_data.split("&"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                params[key] = value

        if "hash" not in params:
            return None

        received_hash = params.pop("hash")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode("utf-8"),
            hashlib.sha256
        ).digest()
        
        calculated_hash = hmac.new(
            secret_key,
            data_check.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None
        
        return params
    except Exception:
        return None


@app.on_event("startup")
async def startup():
    await init_db()


@app.post("/api/click", response_model=ClickResponse)
async def click(req: ClickRequest, db: AsyncSession = Depends(get_db)):
    """Построитка и валидация пользователя через Telegram initData"""
    validated = validate_telegram_init_data(req.init_data, BOT_TOKEN)
    if not validated:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    try:
        telegram_id = int(validated.get("user", {}).get("id", 0))
        if telegram_id == 0:
            raise HTTPException(status_code=400, detail="User ID not found in initData")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid user ID in initData")

    username = validated.get("user", {}).get("username")

    user = await db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, username=username, click_count=0)
        db.add(user)
        await db.commit()

    user.click_count += 1
    await db.commit()
    await db.refresh(user)

    global_stat = await db.query(GlobalStats).first()
    if not global_stat:
        global_stat = GlobalStats(total_clicks=0)
        db.add(global_stat)
        await db.commit()

    global_stat.total_clicks += 1
    await db.commit()

    return ClickResponse(success=True, user_id=telegram_id, new_click_count=user.click_count)


@app.post("/api/create-stars-invoice")
async def create_stars_invoice(req: StarsInvoiceRequest):
    """Создание инвойса для Telegram Stars"""
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

    prices = []
    if req.booster_type == "x2":
        prices = [{"label": "Бустер X2", "amount": 50}]
    elif req.booster_type == "x3":
        prices = [{"label": "Бустер X3", "amount": 100}]
    elif req.booster_type == "x5":
        prices = [{"label": "Бустер X5", "amount": 200}]
    else:
        raise HTTPException(status_code=400, detail="Invalid booster type")

    payload = f"boost_{req.booster_type}_{req.user_id}"

    async with AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink",
            json={
                "title": "Ускоритель X2",
                "description": "Удваивает количество очков за каждый клик!",
                "payload": payload,
                "provider_token": "",
                "currency": "XTR",
                "prices": prices,
            },
        )
        result = resp.json()
        if not result.get("ok"):
            raise HTTPException(status_code=500, detail="Telegram API error")
        return {"success": True, "invoice_url": result["result"]}


@app.get("/api/check-payment-status/{invoice_short_id}")
async def check_payment_status(invoice_short_id: str):
    """Проверка статуса оплаты и зачисление буста"""
    raise HTTPException(status_code=501, detail="Payment status check not implemented yet")


@app.post("/api/telegram-webhook")
async def telegram_webhook(event: dict, db: AsyncSession = Depends(get_db)):
    """Обработка вебхука Telegram для pre_checkout_query и successful_payment"""
    update_type = event.get("update_id")
    if update_type is None:
        raise HTTPException(status_code=400, detail="Invalid update")

    message = event.get("message", {})
    pre_checkout = message.get("pre_checkout_query")
    successful = message.get("successful_payment")

    if pre_checkout:
        query_id = pre_checkout.get("id")
        payload = pre_checkout.get("payload", "")
        return {"ok": True, "pre_checkout_query_id": query_id, "payload": payload}

    if successful:
        payload = successful.get("payload", "")
        telegram_id = successful.get("from", {}).get("id")
        invoice_id = successful.get("invoice_id")

        user = await db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        parts = payload.split("_")
        if len(parts) >= 2:
            booster_type = parts[1]
            await db.query(User).filter(User.telegram_id == telegram_id).update({
                User.purchases: User.purchases.cast(String) + f"{booster_type},"
            })
            await db.commit()
        return {"ok": True, "user_id": telegram_id, "booster_type": booster_type}

    raise HTTPException(status_code=400, detail="Unsupported update type")


@app.post("/api/apply-boost")
async def apply_boost_endpoint(user_id: int, booster_type: str):
    """Применение буста для пользователя"""
    # TODO: Реализовать применение буста через Telegram Bot API
    # Пример: GET https://api.telegram.org/bot<BOT_TOKEN>/getInvoiceLink
    raise HTTPException(status_code=501, detail="Boost application not implemented yet")


@app.get("/api/stats", response_model=StatsResponse)
async def stats(db: AsyncSession = Depends(get_db)):
    """Получение статистики: личные клики и глобальный счётчик"""
    user = await db.query(User).first()
    user_clicks = user.click_count if user else 0

    global_stat = await db.query(GlobalStats).first()
    global_clicks = global_stat.total_clicks if global_stat else 0

    return StatsResponse(user_clicks=user_clicks, global_clicks=global_clicks)
