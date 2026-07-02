"""
===================================================================
Project: Wolf Host - Private Bot Hosting Dashboard
Author: White Wolf
Telegram: https://t.me/j49_c
Year: 2026
License: MIT
Description: Integration test script for end-to-end platform verification
===================================================================
"""

import asyncio
import io
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

BASE_URL = os.getenv("WOLF_HOST_URL", "http://localhost:7860")
ADMIN_USER = os.getenv("ADMIN_USERNAME", "wolf")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "wolf123456")

TEST_BOT_NAME = "test_integration_bot"
PASS_COUNT = 0
FAIL_COUNT = 0


def log_pass(test_name: str) -> None:
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"  [PASS] {test_name}")


def log_fail(test_name: str, reason: str) -> None:
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"  [FAIL] {test_name}: {reason}")


def create_test_bot_zip() -> bytes:
    """Create an in-memory ZIP containing a minimal Python bot."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "main.py",
            "import time\nimport sys\n"
            "print('WolfHostTestBot started', flush=True)\n"
            "while True:\n"
            "    print('heartbeat', flush=True)\n"
            "    time.sleep(2)\n",
        )
        zf.writestr(
            "requirements.txt",
            "",
        )
    return buf.getvalue()


def create_corrupt_zip() -> bytes:
    """Create a ZIP with a missing main script (no .py or .php files)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("readme.txt", "This bot has no script.")
    return buf.getvalue()


def create_empty_zip() -> bytes:
    """Create an empty ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        pass
    return buf.getvalue()


async def run_tests() -> None:
    """Execute all integration tests sequentially."""
    print("=" * 60)
    print("  Wolf Host - Integration Test Suite")
    print("=" * 60)
    print()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        await test_health(client)
        token = await test_login(client)
        if not token:
            print("\n[ABORT] Cannot proceed without valid token.")
            return

        headers = {"Authorization": f"Bearer {token}"}

        await test_upload_valid_bot(client, headers)
        await test_upload_empty_zip(client, headers)
        await test_upload_corrupt_zip(client, headers)
        await test_upload_missing_script(client, headers)
        await test_start_bot(client, headers)
        await asyncio.sleep(2)
        await test_read_logs(client, headers)
        await test_stop_bot(client, headers)
        await test_delete_bot(client, headers)
        await test_auth_required(client)

    print()
    print("=" * 60)
    print(f"  Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 60)


async def test_health(client: httpx.AsyncClient) -> None:
    """Test GET /health endpoint."""
    print("[TEST] Health Check")
    try:
        resp = await client.get("/health")
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            log_pass("Health endpoint returns ok")
        else:
            log_fail("Health endpoint", f"Status {resp.status_code}")
    except Exception as e:
        log_fail("Health endpoint", str(e))


async def test_login(client: httpx.AsyncClient) -> str | None:
    """Test POST /api/login with valid and invalid credentials."""
    print("[TEST] Authentication")

    try:
        resp = await client.post("/api/login", json={
            "username": ADMIN_USER,
            "password": ADMIN_PASS,
        })
        if resp.status_code == 200 and "access_token" in resp.json():
            log_pass("Valid login returns token")
            return resp.json()["access_token"]
        else:
            log_fail("Valid login", f"Status {resp.status_code}")
    except Exception as e:
        log_fail("Valid login", str(e))

    try:
        resp = await client.post("/api/login", json={
            "username": "wrong",
            "password": "wrong",
        })
        if resp.status_code == 401:
            log_pass("Invalid login rejected with 401")
        else:
            log_fail("Invalid login", f"Expected 401, got {resp.status_code}")
    except Exception as e:
        log_fail("Invalid login", str(e))

    return None


async def test_upload_valid_bot(client: httpx.AsyncClient, headers: dict) -> None:
    """Test uploading a valid bot ZIP."""
    print("[TEST] Upload Valid Bot")
    try:
        zip_data = create_test_bot_zip()
        resp = await client.post(
            "/api/bots/upload",
            headers=headers,
            data={"name": TEST_BOT_NAME},
            files={"file": ("test_bot.zip", zip_data, "application/zip")},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("bot_type") == "python":
                log_pass(f"Bot uploaded (type={data['bot_type']}, script={data['script']})")
            else:
                log_fail("Upload bot", f"Unexpected type: {data.get('bot_type')}")
        else:
            log_fail("Upload bot", f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_fail("Upload bot", str(e))


async def test_upload_empty_zip(client: httpx.AsyncClient, headers: dict) -> None:
    """Test uploading an empty ZIP file."""
    print("[TEST] Upload Empty ZIP")
    try:
        zip_data = create_empty_zip()
        resp = await client.post(
            "/api/bots/upload",
            headers=headers,
            data={"name": "empty_bot"},
            files={"file": ("empty.zip", zip_data, "application/zip")},
        )
        if resp.status_code == 400:
            log_pass("Empty ZIP rejected with 400")
        else:
            log_fail("Empty ZIP", f"Expected 400, got {resp.status_code}")
    except Exception as e:
        log_fail("Empty ZIP", str(e))


async def test_upload_corrupt_zip(client: httpx.AsyncClient, headers: dict) -> None:
    """Test uploading a ZIP with no valid script."""
    print("[TEST] Upload Corrupt ZIP (no script)")
    try:
        zip_data = create_corrupt_zip()
        resp = await client.post(
            "/api/bots/upload",
            headers=headers,
            data={"name": "corrupt_bot"},
            files={"file": ("corrupt.zip", zip_data, "application/zip")},
        )
        if resp.status_code == 400:
            log_pass("Corrupt ZIP rejected with 400")
        else:
            log_fail("Corrupt ZIP", f"Expected 400, got {resp.status_code}")
    except Exception as e:
        log_fail("Corrupt ZIP", str(e))


async def test_upload_missing_script(client: httpx.AsyncClient, headers: dict) -> None:
    """Test uploading a ZIP with only a requirements.txt."""
    print("[TEST] Upload Bot Missing Script")
    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("requirements.txt", "requests==2.31.0\n")
        zip_data = buf.getvalue()
        resp = await client.post(
            "/api/bots/upload",
            headers=headers,
            data={"name": "no_script_bot"},
            files={"file": ("noscript.zip", zip_data, "application/zip")},
        )
        if resp.status_code == 400:
            log_pass("Missing script rejected with 400")
        else:
            log_fail("Missing script", f"Expected 400, got {resp.status_code}")
    except Exception as e:
        log_fail("Missing script", str(e))


async def test_start_bot(client: httpx.AsyncClient, headers: dict) -> None:
    """Test starting a bot."""
    print("[TEST] Start Bot")
    try:
        resp = await client.post(
            f"/api/bots/{TEST_BOT_NAME}/start",
            headers=headers,
        )
        if resp.status_code == 200:
            log_pass("Bot started successfully")
        else:
            log_fail("Start bot", f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_fail("Start bot", str(e))


async def test_read_logs(client: httpx.AsyncClient, headers: dict) -> None:
    """Test reading bot logs."""
    print("[TEST] Read Logs")
    try:
        resp = await client.get(
            f"/api/bots/{TEST_BOT_NAME}/logs",
            headers=headers,
            params={"lines": 50},
        )
        if resp.status_code == 200:
            logs = resp.json().get("logs", [])
            if isinstance(logs, list):
                log_pass(f"Logs retrieved ({len(logs)} lines)")
            else:
                log_fail("Read logs", "Logs field is not a list")
        else:
            log_fail("Read logs", f"Status {resp.status_code}")
    except Exception as e:
        log_fail("Read logs", str(e))


async def test_stop_bot(client: httpx.AsyncClient, headers: dict) -> None:
    """Test stopping a bot."""
    print("[TEST] Stop Bot")
    try:
        resp = await client.post(
            f"/api/bots/{TEST_BOT_NAME}/stop",
            headers=headers,
        )
        if resp.status_code == 200:
            log_pass("Bot stopped successfully")
        else:
            log_fail("Stop bot", f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_fail("Stop bot", str(e))


async def test_delete_bot(client: httpx.AsyncClient, headers: dict) -> None:
    """Test deleting a bot."""
    print("[TEST] Delete Bot")
    try:
        resp = await client.delete(
            f"/api/bots/{TEST_BOT_NAME}",
            headers=headers,
        )
        if resp.status_code == 200:
            log_pass("Bot deleted successfully")
        else:
            log_fail("Delete bot", f"Status {resp.status_code}")
    except Exception as e:
        log_fail("Delete bot", str(e))


async def test_auth_required(client: httpx.AsyncClient) -> None:
    """Test that protected endpoints require authentication."""
    print("[TEST] Authentication Required")
    try:
        resp = await client.get("/api/bots")
        if resp.status_code == 401:
            log_pass("Unauthenticated request rejected with 401")
        else:
            log_fail("Auth required", f"Expected 401, got {resp.status_code}")
    except Exception as e:
        log_fail("Auth required", str(e))


if __name__ == "__main__":
    asyncio.run(run_tests())
