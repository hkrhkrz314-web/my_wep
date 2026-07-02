"""
===================================================================
Project: Wolf Host - لوحة استضافة البوتات
Author: @BLACK_ZERO2
Channel: https://t.me/ROXScripts2
Year: 2026
License: MIT
===================================================================
"""

import asyncio
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, get_current_user, verify_password, verify_username
from bot_manager import SecurityError, bot_manager
from config import settings
from database import Bot, BotStatus, BotType, get_session, init_db

app = FastAPI(
    title="Wolf Host",
    description="Private Bot Hosting Dashboard",
    version="2.0.0",
)


class LoginRequest(BaseModel):
    """Login credentials payload."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"


class BotResponse(BaseModel):
    """Bot details response model."""
    id: int
    name: str
    bot_type: str
    script_file: str
    pid: Optional[int]
    status: str
    auto_restart: bool
    restart_count: int
    created_at: datetime
    last_started_at: Optional[datetime]
    last_stopped_at: Optional[datetime]
    error_message: Optional[str]


@app.on_event("startup")
async def startup() -> None:
    """Initialize database, directories, clean stale PIDs, and start watchdog."""
    os.makedirs(settings.BOTS_DIR, exist_ok=True)
    os.makedirs(settings.LOGS_DIR, exist_ok=True)
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    os.makedirs(settings.TMP_DIR, exist_ok=True)
    await init_db()
    await bot_manager.cleanup_stale_pids()
    asyncio.create_task(_watchdog_loop())


async def _watchdog_loop() -> None:
    """Background loop that periodically checks bot health."""
    while True:
        try:
            await bot_manager.check_all_bots()
        except Exception as e:
            print(f"[Watchdog] Error: {e}")
        await asyncio.sleep(settings.WATCHDOG_INTERVAL)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint for uptime monitoring."""
    return {"status": "ok", "service": "Wolf Host", "version": "2.0.0"}


@app.post("/api/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    """Authenticate admin and return a JWT token.

    Args:
        req: Login credentials.

    Returns:
        JWT access token.

    Raises:
        HTTPException: 401 if credentials are invalid.
    """
    if not verify_username(req.username) or not verify_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": req.username})
    return TokenResponse(access_token=token)


@app.get("/api/bots", response_model=list[BotResponse])
async def list_bots(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[BotResponse]:
    """List all registered bots with live status.

    Returns:
        List of BotResponse objects.
    """
    result = await session.execute(select(Bot).order_by(Bot.created_at.desc()))
    bots = result.scalars().all()
    response = []
    for bot in bots:
        actual_status = bot_manager.get_bot_status(bot.name, bot.pid)
        if actual_status != bot.status:
            bot.status = actual_status
            await session.commit()
        response.append(
            BotResponse(
                id=bot.id,
                name=bot.name,
                bot_type=bot.bot_type,
                script_file=bot.script_file,
                pid=bot.pid,
                status=actual_status,
                auto_restart=bot.auto_restart,
                restart_count=bot.restart_count,
                created_at=bot.created_at,
                last_started_at=bot.last_started_at,
                last_stopped_at=bot.last_stopped_at,
                error_message=bot.error_message,
            )
        )
    return response


@app.post("/api/bots/upload")
async def upload_bot(
    name: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upload and install a new bot from a ZIP archive.

    Args:
        name: Bot name (alphanumeric, hyphens, underscores).
        file: ZIP archive containing bot source code.

    Returns:
        Upload result with bot type, script, and install status.

    Raises:
        HTTPException: 400 on validation or extraction failure.
    """
    try:
        name = bot_manager._validate_bot_name(name)
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing = await session.execute(select(Bot).where(Bot.name == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Bot name already exists.")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Only .zip is accepted.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB}MB.",
        )

    bot_dir = bot_manager.get_bot_dir(name)
    os.makedirs(bot_dir, exist_ok=True)

    zip_path = os.path.join(settings.TMP_DIR, f"{name}.zip")
    try:
        with open(zip_path, "wb") as f:
            f.write(content)

        shutil.unpack_archive(zip_path, bot_dir)

        for extracted in Path(bot_dir).rglob("*"):
            if extracted.is_file():
                real = extracted.resolve()
                if not str(real).startswith(str(Path(bot_dir).resolve())):
                    shutil.rmtree(bot_dir, ignore_errors=True)
                    raise HTTPException(
                        status_code=400,
                        detail="Malicious path detected in archive.",
                    )
    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(bot_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to extract: {e}")
    finally:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError:
                pass

    bot_type = bot_manager.detect_bot_type(bot_dir)
    script_file = bot_manager.find_main_script(bot_dir, bot_type)

    if not script_file:
        shutil.rmtree(bot_dir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="No main script found (main.py, bot.py, bot.php, etc).",
        )

    install_ok, install_msg = await bot_manager.install_dependencies(
        name, bot_dir, bot_type
    )

    new_bot = Bot(
        name=name,
        bot_type=bot_type.value,
        script_file=script_file,
        directory=bot_dir,
        status=BotStatus.STOPPED.value,
    )
    session.add(new_bot)
    await session.commit()

    return {
        "message": "Bot uploaded successfully",
        "bot_type": bot_type.value,
        "script": script_file,
        "dependencies": "installed" if install_ok else "failed",
        "install_log": install_msg[:500],
    }


@app.post("/api/bots/{bot_name}/start")
async def start_bot(
    bot_name: str,
    user=Depends(get_current_user),
) -> dict:
    """Start a bot process in the background.

    Args:
        bot_name: Name of the bot to start.

    Returns:
        Status message.
    """
    try:
        ok, msg = await bot_manager.start_bot(bot_name)
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


@app.post("/api/bots/{bot_name}/stop")
async def stop_bot(
    bot_name: str,
    user=Depends(get_current_user),
) -> dict:
    """Stop a running bot process.

    Args:
        bot_name: Name of the bot to stop.

    Returns:
        Status message.
    """
    try:
        ok, msg = await bot_manager.stop_bot(bot_name)
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


@app.post("/api/bots/{bot_name}/restart")
async def restart_bot(
    bot_name: str,
    user=Depends(get_current_user),
) -> dict:
    """Restart a bot (stop then start).

    Args:
        bot_name: Name of the bot to restart.

    Returns:
        Status message.
    """
    try:
        ok, msg = await bot_manager.restart_bot(bot_name)
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


@app.delete("/api/bots/{bot_name}")
async def delete_bot(
    bot_name: str,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Delete a bot and remove all its files.

    Args:
        bot_name: Name of the bot to delete.

    Returns:
        Status message.
    """
    try:
        await bot_manager.stop_bot(bot_name)
        bot_dir = bot_manager.get_bot_dir(bot_name)
        log_path = bot_manager.get_log_path(bot_name)
        pid_path = bot_manager.get_pid_path(bot_name)
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await session.execute(select(Bot).where(Bot.name == bot_name))
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found.")

    await session.delete(bot)
    await session.commit()

    for path in [bot_dir, log_path, pid_path]:
        if path and os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
            except OSError:
                pass

    return {"message": "Bot deleted."}


@app.get("/api/bots/{bot_name}/logs")
async def get_logs(
    bot_name: str,
    lines: int = Query(100, ge=1, le=1000),
    user=Depends(get_current_user),
) -> dict:
    """Retrieve the last N lines of a bot's log.

    Args:
        bot_name: Name of the bot.
        lines: Number of lines to retrieve.

    Returns:
        Dict with 'logs' list.
    """
    try:
        log_lines = bot_manager.get_log_lines(bot_name, lines)
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"logs": log_lines}


@app.websocket("/ws/logs/{bot_name}")
async def websocket_logs(websocket: WebSocket, bot_name: str) -> None:
    """WebSocket endpoint for streaming live bot logs.

    Includes a periodic heartbeat ping every 10 seconds to prevent
    Cloudflare proxy from dropping idle connections.

    Args:
        websocket: The WebSocket connection.
        bot_name: Name of the bot to stream logs for.
    """
    try:
        bot_manager._validate_bot_name(bot_name)
    except SecurityError:
        await websocket.close(code=4003, reason="Invalid bot name")
        return

    await websocket.accept()
    last_line_count = 0
    last_heartbeat = asyncio.get_event_loop().time()

    try:
        while True:
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat >= settings.WS_HEARTBEAT_INTERVAL:
                try:
                    await websocket.send_json({"type": "ping"})
                    last_heartbeat = now
                except Exception:
                    break

            log_path = bot_manager.get_log_path(bot_name)
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        all_lines = f.readlines()
                        if len(all_lines) > last_line_count:
                            new_lines = [
                                line.rstrip("\n")
                                for line in all_lines[last_line_count:]
                            ]
                            await websocket.send_json(
                                {"type": "logs", "lines": new_lines}
                            )
                            last_line_count = len(all_lines)
                except Exception:
                    pass
            else:
                if last_line_count > 0:
                    await websocket.send_json(
                        {"type": "logs", "lines": ["[Log file cleared]"]}
                    )
                    last_line_count = 0

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@app.post("/api/bots/{bot_name}/toggle-autorestart")
async def toggle_autorestart(
    bot_name: str,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Toggle the auto-restart flag for a bot.

    Args:
        bot_name: Name of the bot.

    Returns:
        Dict with updated auto_restart boolean.
    """
    try:
        name = bot_manager._validate_bot_name(bot_name)
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await session.execute(select(Bot).where(Bot.name == name))
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found.")
    bot.auto_restart = not bot.auto_restart
    await session.commit()
    return {"auto_restart": bot.auto_restart}


@app.get("/", response_class=HTMLResponse)
async def serve_ui() -> HTMLResponse:
    """Serve the main dashboard HTML page."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        content="<h1>Wolf Host - Dashboard not found</h1>",
        status_code=404,
    )
