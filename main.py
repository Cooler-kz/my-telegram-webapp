import traceback
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, init_db, User, GlobalStats


app = FastAPI(title="Telegram Clicker API")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def read_root():
    return FileResponse("index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


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
    # Мягкая валидация - разрешаем тестирование без initData
    if req.init_data and BOT_TOKEN:
        validated = validate_telegram_init_data(req.init_data, BOT_TOKEN)
        if not validated:
            raise HTTPException(status_code=401, detail="Invalid Telegram initData")
    else:
        validated = {}

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

    # Учёт активного буста при начислении очков
    multiplier = 1.0
    if user.boost_expires_at and user.boost_expires_at > datetime.utcnow():
        multiplier = user.boost_multiplier
    else:
        user.boost_multiplier = 1.0
        user.boost_expires_at = None

    user.click_count += int(multiplier)
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


@app.post("/api/click", response_model=ClickResponse)
async def click(req: ClickRequest, db: AsyncSession = Depends(get_db)):
    """Построитка и валидация пользователя через Telegram initData"""
    # Мягкая валидация - разрешаем тестирование без initData
    if req.init_data and BOT_TOKEN:
        validated = validate_telegram_init_data(req.init_data, BOT_TOKEN)
        if not validated:
            raise HTTPException(status_code=401, detail="Invalid Telegram initData")
    else:
        validated = {}

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

    # Учёт активного буста при начислении очков
    multiplier = 1.0
    if user.boost_expires_at and user.boost_expires_at > datetime.utcnow():
        multiplier = user.boost_multiplier
    else:
        user.boost_multiplier = 1.0
        user.boost_expires_at = None

    user.click_count += int(multiplier)
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
async def check_payment_status(invoice_short_id: str, db: AsyncSession = Depends(get_db)):
    """Проверка статуса оплаты и зачисление буста"""
    # Ищем покупку по invoice_id в поле purchases (упрощённая реализация)
    user = await db.query(User).filter(User.purchases.like(f"%{invoice_short_id}%")).first()
    if user:
        return {"status": "paid", "user_id": user.id}
    return {"status": "pending", "user_id": None}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.1"}


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

        # Отправляем ответ на pre_checkout_query через Telegram Bot API
        if not BOT_TOKEN:
            raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

        async with AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery",
                json={
                    "pre_checkout_query_id": query_id,
                    "ok": True,
                },
            )
            result = resp.json()
            if not result.get("ok"):
                raise HTTPException(status_code=500, detail="Telegram answerPreCheckoutQuery API error")

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
async def apply_boost_endpoint(user_id: int, booster_type: str, db: AsyncSession = Depends(get_db)):
    """Применение буста для пользователя"""
    # Mapping booster_type к множителю и длительности
    boost_config = {
        "x2": {"multiplier": 2.0, "duration_minutes": 15},
        "x3": {"multiplier": 3.0, "duration_minutes": 20},
        "x5": {"multiplier": 5.0, "duration_minutes": 30},
    }
    config = boost_config.get(booster_type)
    if not config:
        raise HTTPException(status_code=400, detail="Invalid booster type")

    user = await db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Устанавливаем активный буст
    user.boost_multiplier = config["multiplier"]
    user.boost_expires_at = datetime.utcnow() + timedelta(minutes=config["duration_minutes"])
    await db.commit()

    return {"success": True, "multiplier": config["multiplier"], "expires_at": user.boost_expires_at.isoformat()}


@app.get("/api/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    """Получение статистики: личные клики и глобальный счётчик"""
    try:
        user = await db.query(User).first()
        user_clicks = user.click_count if user else 0

        global_stat = await db.query(GlobalStats).first()
        global_clicks = global_stat.total_clicks if global_stat else 0

        return {"user_score": user_clicks, "global_record": global_clicks}
    except Exception:
        print(traceback.format_exc())
        return {"user_score": 0, "global_record": 0}


@app.get("/api/boost-status")
async def get_boost_status(user_id: int, db: AsyncSession = Depends(get_db)):
    """Получение статуса активного буста пользователя"""
    user = await db.query(User).filter(User.telegram_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    boost_active = False
    multiplier = 1.0
    expires_at = None
    
    if user.boost_expires_at and user.boost_expires_at > datetime.utcnow():
        boost_active = True
        multiplier = user.boost_multiplier
        expires_at = user.boost_expires_at.isoformat()
    
    return {"boost_active": boost_active, "multiplier": multiplier, "expires_at": expires_at}


@app.post("/api/claim-ad-reward")
async def claim_ad_reward(user_id: int, db: AsyncSession = Depends(get_db)):
    """Начисление вознаграждения за просмотр рекламы (+100 очков)"""
    user = await db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Начисляем 100 очков
    user.click_count += 100
    await db.commit()
    await db.refresh(user)
    
    return {"success": True, "balance": user.click_count}
