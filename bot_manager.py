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
import re
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import Bot, BotStatus, BotType, async_session

BOT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


class SecurityError(Exception):
    """Raised when a security check fails (e.g. path traversal)."""


class BotManager:
    """Core service for managing bot processes, PIDs, logs, and dependencies."""

    def __init__(self) -> None:
        os.makedirs(settings.BOTS_DIR, exist_ok=True)
        os.makedirs(settings.LOGS_DIR, exist_ok=True)
        os.makedirs(settings.DATA_DIR, exist_ok=True)
        os.makedirs(settings.TMP_DIR, exist_ok=True)

    @staticmethod
    def _validate_bot_name(name: str) -> str:
        """Validate bot name to prevent path traversal and injection attacks.

        Args:
            name: The bot name to validate.

        Returns:
            The validated sanitized name.

        Raises:
            SecurityError: If the name contains invalid characters or path separators.
        """
        if not name or not BOT_NAME_PATTERN.match(name):
            raise SecurityError(
                f"Invalid bot name: '{name}'. "
                "Names must be 1-64 alphanumeric chars, hyphens, or underscores."
            )
        return name

    @staticmethod
    def _safe_path(base: str, name: str) -> str:
        """Resolve a path and verify it stays within the base directory.

        Args:
            base: The allowed base directory.
            name: The subdirectory or file name.

        Returns:
            Absolute resolved path string.

        Raises:
            SecurityError: If the resolved path escapes the base directory.
        """
        resolved = Path(base).resolve()
        target = (resolved / name).resolve()
        if not str(target).startswith(str(resolved)):
            raise SecurityError(
                f"Path traversal blocked: '{name}' escapes base '{base}'"
            )
        return str(target)

    def get_bot_dir(self, bot_name: str) -> str:
        """Return the safe absolute path for a bot's directory."""
        self._validate_bot_name(bot_name)
        return self._safe_path(settings.BOTS_DIR, bot_name)

    def get_log_path(self, bot_name: str) -> str:
        """Return the safe absolute path for a bot's log file."""
        self._validate_bot_name(bot_name)
        log_file = f"{bot_name}.log"
        resolved_base = Path(settings.LOGS_DIR).resolve()
        target = (resolved_base / log_file).resolve()
        if not str(target).startswith(str(resolved_base)):
            raise SecurityError("Path traversal detected in log path")
        return str(target)

    def get_pid_path(self, bot_name: str) -> str:
        """Return the safe absolute path for a bot's PID file."""
        self._validate_bot_name(bot_name)
        pid_file = f"{bot_name}.pid"
        resolved_base = Path(settings.LOGS_DIR).resolve()
        target = (resolved_base / pid_file).resolve()
        if not str(target).startswith(str(resolved_base)):
            raise SecurityError("Path traversal detected in PID path")
        return str(target)

    def detect_bot_type(self, bot_dir: str) -> BotType:
        """Detect whether a bot is Python or PHP based on project files.

        Args:
            bot_dir: Absolute path to the bot's directory.

        Returns:
            Detected BotType enum value.
        """
        has_composer = os.path.exists(os.path.join(bot_dir, "composer.json"))
        has_requirements = os.path.exists(os.path.join(bot_dir, "requirements.txt"))
        has_python = any(
            f.endswith(".py")
            for f in os.listdir(bot_dir)
            if os.path.isfile(os.path.join(bot_dir, f))
        )

        if has_composer and not has_python:
            return BotType.PHP
        if has_requirements or has_python:
            return BotType.PYTHON
        if has_composer:
            return BotType.PHP
        return BotType.PYTHON

    def find_main_script(self, bot_dir: str, bot_type: BotType) -> str:
        """Locate the primary entry-point script for a bot.

        Args:
            bot_dir: Absolute path to the bot's directory.
            bot_type: Detected bot runtime type.

        Returns:
            Filename of the main script, or empty string if not found.
        """
        if bot_type == BotType.PHP:
            candidates = ["bot.php", "main.php", "index.php"]
            for name in candidates:
                if os.path.exists(os.path.join(bot_dir, name)):
                    return name
            php_files = [
                f
                for f in os.listdir(bot_dir)
                if f.endswith(".php")
                and os.path.isfile(os.path.join(bot_dir, f))
            ]
            return php_files[0] if php_files else ""

        candidates = ["main.py", "bot.py", "app.py", "run.py", "start.py"]
        for name in candidates:
            if os.path.exists(os.path.join(bot_dir, name)):
                return name
        py_files = [
            f
            for f in os.listdir(bot_dir)
            if f.endswith(".py") and os.path.isfile(os.path.join(bot_dir, f))
        ]
        return py_files[0] if py_files else ""

    async def install_dependencies(
        self, bot_name: str, bot_dir: str, bot_type: BotType
    ) -> tuple[bool, str]:
        """Install dependencies for a bot based on its runtime type.

        Args:
            bot_name: Name of the bot (for logging).
            bot_dir: Absolute path to the bot's directory.
            bot_type: Runtime type (PYTHON or PHP).

        Returns:
            Tuple of (success: bool, output_message: str).
        """
        try:
            if bot_type == BotType.PYTHON:
                req_file = os.path.join(bot_dir, "requirements.txt")
                if not os.path.exists(req_file):
                    return True, "No requirements.txt found, skipping."

                proc = await asyncio.create_subprocess_exec(
                    "pip", "install", "--quiet", "-r", req_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=bot_dir,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                if proc.returncode != 0:
                    return False, stderr.decode(errors="replace")[:2000]
                return True, stdout.decode(errors="replace")[:2000]

            if bot_type == BotType.PHP:
                composer_json = os.path.join(bot_dir, "composer.json")
                if not os.path.exists(composer_json):
                    return True, "No composer.json found, skipping."

                proc = await asyncio.create_subprocess_exec(
                    "composer", "install", "--no-interaction", "--no-dev",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=bot_dir,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                if proc.returncode != 0:
                    return False, stderr.decode(errors="replace")[:2000]
                return True, stdout.decode(errors="replace")[:2000]

            return True, "Unknown bot type, skipping."

        except asyncio.TimeoutError:
            return False, "Dependency installation timed out after 300 seconds."
        except Exception as e:
            return False, f"Dependency install error: {e}"

    async def start_bot(self, bot_name: str) -> tuple[bool, str]:
        """Start a bot process in the background.

        Args:
            bot_name: Name of the bot to start.

        Returns:
            Tuple of (success: bool, message: str).
        """
        self._validate_bot_name(bot_name)

        async with async_session() as session:
            result = await session.execute(
                select(Bot).where(Bot.name == bot_name)
            )
            bot = result.scalar_one_or_none()
            if not bot:
                return False, "Bot not found."

            if bot.status == BotStatus.RUNNING.value and bot.pid:
                if psutil.pid_exists(bot.pid):
                    return True, "Bot is already running."
                bot.status = BotStatus.STOPPED.value
                bot.pid = None
                await session.commit()

            bot_dir = self.get_bot_dir(bot_name)
            log_path = self.get_log_path(bot_name)

            if not os.path.exists(bot_dir):
                return False, "Bot directory not found."

            script = bot.script_file
            script_path = os.path.join(bot_dir, script)
            if not os.path.exists(script_path):
                return False, f"Script not found: {script}"

            try:
                log_file = open(log_path, "w", encoding="utf-8")

                if bot.bot_type == BotType.PHP.value:
                    cmd = ["php", script]
                else:
                    cmd = ["python", "-u", script]

                process = subprocess.Popen(
                    cmd,
                    cwd=bot_dir,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )

                pid = process.pid
                pid_path = self.get_pid_path(bot_name)
                with open(pid_path, "w", encoding="utf-8") as pf:
                    pf.write(str(pid))

                bot.pid = pid
                bot.status = BotStatus.RUNNING.value
                bot.last_started_at = datetime.utcnow()
                bot.error_message = None
                await session.commit()

                return True, f"Bot started with PID {pid}"

            except FileNotFoundError as e:
                bot.status = BotStatus.CRASHED.value
                bot.error_message = f"Binary not found: {e}"
                await session.commit()
                return False, bot.error_message
            except PermissionError as e:
                bot.status = BotStatus.CRASHED.value
                bot.error_message = f"Permission denied: {e}"
                await session.commit()
                return False, bot.error_message
            except Exception as e:
                bot.status = BotStatus.CRASHED.value
                bot.error_message = str(e)[:500]
                await session.commit()
                return False, str(e)

    def _force_kill_process(self, pid: int) -> None:
        """Force-kill a process and all its children.

        Args:
            pid: The process ID to kill.
        """
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            parent.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    async def stop_bot(self, bot_name: str) -> tuple[bool, str]:
        """Stop a running bot process and clean up PID tracking.

        Args:
            bot_name: Name of the bot to stop.

        Returns:
            Tuple of (success: bool, message: str).
        """
        self._validate_bot_name(bot_name)

        async with async_session() as session:
            result = await session.execute(
                select(Bot).where(Bot.name == bot_name)
            )
            bot = result.scalar_one_or_none()
            if not bot:
                return False, "Bot not found."

            if bot.pid and psutil.pid_exists(bot.pid):
                self._force_kill_process(bot.pid)

            pid_path = self.get_pid_path(bot_name)
            if os.path.exists(pid_path):
                try:
                    os.remove(pid_path)
                except OSError:
                    pass

            bot.pid = None
            bot.status = BotStatus.STOPPED.value
            bot.last_stopped_at = datetime.utcnow()
            await session.commit()

            return True, "Bot stopped."

    async def restart_bot(self, bot_name: str) -> tuple[bool, str]:
        """Restart a bot by stopping then starting it.

        Args:
            bot_name: Name of the bot to restart.

        Returns:
            Tuple of (success: bool, message: str).
        """
        self._validate_bot_name(bot_name)
        await self.stop_bot(bot_name)
        await asyncio.sleep(1)
        start_ok, start_msg = await self.start_bot(bot_name)

        if start_ok:
            async with async_session() as session:
                result = await session.execute(
                    select(Bot).where(Bot.name == bot_name)
                )
                bot = result.scalar_one_or_none()
                if bot:
                    bot.restart_count += 1
                    await session.commit()

        return start_ok, start_msg

    def get_bot_status(self, bot_name: str, pid: Optional[int]) -> str:
        """Check live process status by PID.

        Args:
            bot_name: Name of the bot (unused, kept for interface).
            pid: Process ID to check.

        Returns:
            Current BotStatus value string.
        """
        if pid and psutil.pid_exists(pid):
            return BotStatus.RUNNING.value
        return BotStatus.STOPPED.value

    def get_log_lines(self, bot_name: str, lines: int = 100) -> list[str]:
        """Read the last N lines from a bot's log file.

        Args:
            bot_name: Name of the bot.
            lines: Maximum number of lines to return.

        Returns:
            List of log line strings.
        """
        log_path = self.get_log_path(bot_name)
        if not os.path.exists(log_path):
            return []
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                return [line.rstrip("\n") for line in all_lines[-lines:]]
        except Exception:
            return []

    async def cleanup_stale_pids(self) -> None:
        """Clean up stale PIDs from database on startup or container restart.

        Scans all bots marked as 'running' and verifies their PIDs still exist.
        Bots with dead PIDs are marked as 'stopped'.
        """
        async with async_session() as session:
            result = await session.execute(
                select(Bot).where(Bot.status == BotStatus.RUNNING.value)
            )
            stale_bots = result.scalars().all()

            for bot in stale_bots:
                if bot.pid and not psutil.pid_exists(bot.pid):
                    bot.status = BotStatus.STOPPED.value
                    bot.pid = None
                    pid_path = self.get_pid_path(bot.name)
                    if os.path.exists(pid_path):
                        try:
                            os.remove(pid_path)
                        except OSError:
                            pass

            await session.commit()

    def kill_rogue_bot(self, pid: int, max_memory_mb: int = 512) -> bool:
        """Check if a bot exceeds memory limits and kill it.

        Args:
            pid: Process ID to check.
            max_memory_mb: Maximum allowed memory in megabytes.

        Returns:
            True if the process was killed, False otherwise.
        """
        try:
            proc = psutil.Process(pid)
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            if mem_mb > max_memory_mb:
                self._force_kill_process(pid)
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return False

    async def check_all_bots(self) -> None:
        """Watchdog: verify all bots are alive, restart crashed ones, kill rogues."""
        async with async_session() as session:
            result = await session.execute(select(Bot))
            bots = result.scalars().all()

            for bot in bots:
                try:
                    if bot.status == BotStatus.RUNNING.value:
                        if bot.pid:
                            if not psutil.pid_exists(bot.pid):
                                bot.status = BotStatus.CRASHED.value
                                bot.pid = None
                                pid_path = self.get_pid_path(bot.name)
                                if os.path.exists(pid_path):
                                    try:
                                        os.remove(pid_path)
                                    except OSError:
                                        pass
                                if bot.auto_restart:
                                    await session.commit()
                                    try:
                                        await self.start_bot(bot.name)
                                    except Exception:
                                        pass
                                continue

                            if self.kill_rogue_bot(bot.pid):
                                bot.status = BotStatus.CRASHED.value
                                bot.pid = None
                                bot.error_message = "Killed: exceeded memory limit"
                                if bot.auto_restart:
                                    await session.commit()
                                    try:
                                        await self.start_bot(bot.name)
                                    except Exception:
                                        pass
                                continue

                        elif not bot.pid:
                            bot.status = BotStatus.STOPPED.value
                except Exception:
                    pass

                try:
                    await session.commit()
                except Exception:
                    await session.rollback()


bot_manager = BotManager()
