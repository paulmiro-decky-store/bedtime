import asyncio
import json
import os
import signal
import socket
import sys
import time
from datetime import datetime
from typing import Any, Callable, Optional

import decky

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_modules"))

from bedtime_core import (  # noqa: E402
    BedtimeState,
    StateStore,
    normalize_settings,
    parse_hhmm,
    signal_game_processes,
    find_game_reapers,
    status_payload,
    validate_settings_patch,
)
from bedtime_web import BedtimeRejected, WebServer, make_app  # noqa: E402

TICK_SECONDS = 1.0
# After bedtime, give Steam this long to close the game itself before the
# backend starts terminating game processes directly.
GRACE_SECONDS = 20.0
# SIGKILL whatever ignored SIGTERM for this long.
KILL_AFTER_SECONDS = 15.0


def _settings_path() -> str:
    return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")


def _read_user_settings() -> dict[str, Any]:
    try:
        with open(_settings_path(), "r", encoding="utf-8") as fh:
            return normalize_settings(json.load(fh))
    except (OSError, ValueError):
        return normalize_settings(None)


def _write_user_settings(data: dict[str, Any]) -> None:
    os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
    tmp = _settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, _settings_path())


def _local_ipv4() -> Optional[str]:
    """Primary LAN address (no packets are sent)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


class Plugin:
    state: Optional[BedtimeState] = None
    store: Optional[StateStore] = None
    server: Optional[WebServer] = None
    _tick_task: Optional[asyncio.Task] = None
    _set_lock: Optional[asyncio.Lock] = None
    _reached_at: Optional[float] = None
    _termed: dict[int, float] = {}

    # ------------------------------------------------------------------ setup

    async def _main(self):
        self._set_lock = asyncio.Lock()
        self._termed = {}
        self.store = StateStore(decky.DECKY_PLUGIN_RUNTIME_DIR)
        self.state = self.store.load()
        if self.state is not None:
            decky.logger.info("Restored bedtime %s for this boot", self.state.bedtime)
            if self.state.reached:
                self._reached_at = time.monotonic() - GRACE_SECONDS
        self.server = WebServer(lambda: make_app(self._status, self._set_bedtime_from_web))
        await self._restart_server()
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def _unload(self):
        if self._tick_task is not None:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        if self.server is not None:
            await self.server.stop()

    async def _uninstall(self):
        if self.store is not None:
            self.store.clear()

    # --------------------------------------------------------------- settings

    async def _restart_server(self) -> None:
        settings = _read_user_settings()
        try:
            await self.server.start(settings["listenAddress"], settings["port"])
            decky.logger.info("Web UI listening on %s:%s", settings["listenAddress"], settings["port"])
        except Exception:
            decky.logger.error("%s", self.server.error)

    # ------------------------------------------------------------------ state

    def _status(self) -> dict[str, Any]:
        settings = _read_user_settings()
        return status_payload(self.state, settings)

    async def _set_bedtime_from_web(self, value: Any) -> dict[str, Any]:
        parse_hhmm(value)  # raises ValueError for bad input
        return await self._apply_bedtime(lambda: BedtimeState.create(value))

    async def _apply_bedtime(self, make_state: Callable[[], BedtimeState]) -> dict[str, Any]:
        """Set a new bedtime; once one is set, only earlier ones are accepted."""
        async with self._set_lock:
            old = self.state
            state = make_state()
            if old is not None:
                # Once set, the bedtime can only be moved earlier.
                if old.reached or old.remaining() <= 0:
                    raise BedtimeRejected("Bedtime has already been reached.")
                if not state.is_earlier_than(old):
                    raise BedtimeRejected(
                        f"Bedtime can only be moved earlier than {old.bedtime}.")
            self.store.save(state)
            self.state = state
        status = self._status()
        status["changed"] = old is not None
        decky.logger.info("Bedtime %s %s (%s left)", "moved to" if old else "set to",
                          state.bedtime, status["remainingText"])
        await decky.emit("bedtime_set", status)
        return status

    async def _tick_loop(self):
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # keep enforcing no matter what
                decky.logger.exception("tick failed: %s", exc)
            await asyncio.sleep(TICK_SECONDS)

    async def _tick(self):
        state = self.state
        if state is None:
            return
        due = state.due_warnings()
        if due:
            state.warned.extend(due)
            self.store.save(state)
            minutes = min(due)
            decky.logger.info("Bedtime warning: %d min left", minutes)
            await decky.emit("bedtime_warning", minutes)

        if state.remaining() <= 0 and not state.reached:
            state.reached = True
            self.store.save(state)
            self._reached_at = time.monotonic()
            decky.logger.info("Bedtime reached, closing games")
            await decky.emit("bedtime_reached")

        if state.reached:
            self._enforce()

    def _enforce(self):
        """Backend fallback: terminate game processes the frontend didn't stop."""
        now = time.monotonic()
        if self._reached_at is None or now - self._reached_at < GRACE_SECONDS:
            return
        reapers = find_game_reapers()
        if not reapers:
            self._termed.clear()
            return
        for pid in list(self._termed):
            if pid not in reapers:
                del self._termed[pid]
        stubborn = [pid for pid, t in self._termed.items() if now - t >= KILL_AFTER_SECONDS]
        if stubborn:
            decky.logger.warning("Killing games that ignored SIGTERM: %s", stubborn)
            signal_game_processes(signal.SIGKILL)
        fresh = [pid for pid in reapers if pid not in self._termed]
        if fresh:
            decky.logger.info("Terminating games: %s", {p: reapers[p] for p in fresh})
            signal_game_processes(signal.SIGTERM)
            for pid in fresh:
                self._termed[pid] = now

    # ---------------------------------------------------- frontend callables

    async def get_status(self) -> dict[str, Any]:
        settings = _read_user_settings()
        status = status_payload(self.state, settings)
        address = self.server.address if self.server else settings["listenAddress"]
        port = self.server.port if self.server else settings["port"]
        host = address
        if address in ("0.0.0.0", "::", ""):
            host = _local_ipv4() or socket.gethostname()
        if ":" in host:
            host = f"[{host}]"
        status.update(
            url=f"http://{host}:{port}/" if self.server and self.server.running else None,
            serverError=self.server.error if self.server else None,
            settings=settings,
            now=datetime.now().isoformat(timespec="seconds"),
        )
        return status

    async def set_bedtime_in(self, minutes: int) -> dict[str, Any]:
        """From the Deck: bedtime `minutes` from now (same rules as the web page)."""
        try:
            BedtimeState.create_in(minutes)  # validate before taking the lock
            await self._apply_bedtime(lambda: BedtimeState.create_in(minutes))
        except (ValueError, BedtimeRejected) as exc:
            raise Exception(str(exc)) from exc
        return await self.get_status()

    async def save_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        try:
            clean = validate_settings_patch(patch)
        except ValueError as exc:
            raise Exception(str(exc)) from exc
        current = _read_user_settings()
        current.update(clean)
        _write_user_settings(current)
        if (current["listenAddress"], current["port"]) != (self.server.address, self.server.port) \
                or not self.server.running:
            await self._restart_server()
        return await self.get_status()
