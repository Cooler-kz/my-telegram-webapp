import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, init_db, User, GlobalStats


app = FastAPI(title="Telegram Clicker API")

BOT_TOKEN = secrets.token_urlsafe(32)  # Замените на токен вашего бота
ALLOWED_ORIGINS = ["https://github.com", "https://<username>.github.io", "https://abc123.ngrok.io"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/stats", response_model=StatsResponse)
async def stats(db: AsyncSession = Depends(get_db)):
    """Получение статистики: личные клики и глобальный счётчик"""
    user = await db.query(User).first()
    user_clicks = user.click_count if user else 0

    global_stat = await db.query(GlobalStats).first()
    global_clicks = global_stat.total_clicks if global_stat else 0

    return StatsResponse(user_clicks=user_clicks, global_clicks=global_clicks)
