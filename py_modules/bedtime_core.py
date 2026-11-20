"""Pure logic for the Bedtime plugin (no Decky imports, unit-testable)."""

from __future__ import annotations

import json
import os
import re
import signal
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

WARN_MINUTES = (15, 5, 1)
DEFAULT_SETTINGS: dict[str, Any] = {
    "defaultBedtime": "21:00",
    "listenAddress": "0.0.0.0",
    "port": 19114,
}
HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# --------------------------------------------------------------------------
# Clocks
# --------------------------------------------------------------------------

def boottime() -> float:
    """Seconds since boot, including time spent suspended.

    Used for the countdown so that changing the wall clock or time zone
    after the bedtime was set does not move the deadline.
    """
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def read_boot_id() -> str:
    try:
        with open("/proc/sys/kernel/random/boot_id", "r", encoding="ascii") as fh:
            return fh.read().strip()
    except OSError:
        return "unknown"


# --------------------------------------------------------------------------
# Time parsing
# --------------------------------------------------------------------------

def parse_hhmm(value: Any) -> tuple[int, int]:
    if not isinstance(value, str):
        raise ValueError("time must be a string in HH:MM format")
    match = HHMM_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid time {value!r}, expected HH:MM (24h)")
    return int(match.group(1)), int(match.group(2))


def next_occurrence(hhmm: str, now: datetime) -> datetime:
    """Next local wall-clock time HH:MM strictly after `now`."""
    hour, minute = parse_hhmm(hhmm)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

def normalize_settings(raw: Any) -> dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        if "defaultBedtime" in raw:
            try:
                h, m = parse_hhmm(raw["defaultBedtime"])
                out["defaultBedtime"] = f"{h:02d}:{m:02d}"
            except ValueError:
                pass
        if isinstance(raw.get("listenAddress"), str) and raw["listenAddress"].strip():
            out["listenAddress"] = raw["listenAddress"].strip()
        port = raw.get("port")
        if isinstance(port, str) and port.strip().isdigit():
            port = int(port.strip())
        if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535:
            out["port"] = port
    return out


def validate_settings_patch(patch: Any) -> dict[str, Any]:
    """Validate a settings change from the UI; raises ValueError on bad input."""
    if not isinstance(patch, dict):
        raise ValueError("settings must be an object")
    clean: dict[str, Any] = {}
    if "defaultBedtime" in patch:
        h, m = parse_hhmm(patch["defaultBedtime"])
        clean["defaultBedtime"] = f"{h:02d}:{m:02d}"
    if "listenAddress" in patch:
        addr = patch["listenAddress"]
        if not isinstance(addr, str) or not addr.strip():
            raise ValueError("listen address must not be empty")
        clean["listenAddress"] = addr.strip()
    if "port" in patch:
        port = patch["port"]
        if isinstance(port, str) and port.strip().isdigit():
            port = int(port.strip())
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError("port must be a number between 1 and 65535")
        clean["port"] = port
    return clean


def load_managed_config(path: str) -> dict[str, Any]:
    """Read settings fixed by the system (e.g. the NixOS module).

    Returns only the keys that are set; those are read-only in the UI.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    managed: dict[str, Any] = {}
    for key in ("listenAddress", "port"):
        if raw.get(key) is not None:
            try:
                managed.update(validate_settings_patch({key: raw[key]}))
            except ValueError:
                pass
    return managed


# --------------------------------------------------------------------------
# Bedtime state (lives only until reboot)
# --------------------------------------------------------------------------

@dataclass
class BedtimeState:
    boot_id: str
    bedtime: str                 # "HH:MM" as entered
    deadline_wall: float         # unix timestamp, for display only
    deadline_boot: float         # CLOCK_BOOTTIME seconds, authoritative
    set_at_wall: float
    warned: list[int] = field(default_factory=list)
    reached: bool = False

    def remaining(self, now_boot: Optional[float] = None) -> float:
        if now_boot is None:
            now_boot = boottime()
        return self.deadline_boot - now_boot

    @classmethod
    def create(cls, hhmm: str, now: Optional[datetime] = None,
               now_boot: Optional[float] = None, boot_id: Optional[str] = None) -> "BedtimeState":
        now = now or datetime.now()
        now_boot = boottime() if now_boot is None else now_boot
        target = next_occurrence(hhmm, now)
        seconds = (target - now).total_seconds()
        h, m = parse_hhmm(hhmm)
        state = cls(
            boot_id=boot_id or read_boot_id(),
            bedtime=f"{h:02d}:{m:02d}",
            deadline_wall=now.timestamp() + seconds,
            deadline_boot=now_boot + seconds,
            set_at_wall=now.timestamp(),
        )
        # Thresholds already passed at set time are not announced separately;
        # the "bedtime set" toast already says how much time is left.
        state.warned = [mins for mins in WARN_MINUTES if seconds <= mins * 60]
        return state

    def is_earlier_than(self, other: "BedtimeState") -> bool:
        """True if this deadline is earlier than `other` (same boot).

        Bedtimes have minute resolution; the margin keeps re-entering the same
        time from passing due to clock jitter between the two calculations.
        """
        return self.boot_id == other.boot_id and self.deadline_boot < other.deadline_boot - 30

    def due_warnings(self, now_boot: Optional[float] = None) -> list[int]:
        """Warning thresholds (minutes) crossed but not yet announced."""
        rem = self.remaining(now_boot)
        if rem <= 0:
            return []
        return [m for m in WARN_MINUTES if rem <= m * 60 and m not in self.warned]

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> "BedtimeState":
        data = json.loads(text)
        return cls(
            boot_id=str(data["boot_id"]),
            bedtime=str(data["bedtime"]),
            deadline_wall=float(data["deadline_wall"]),
            deadline_boot=float(data["deadline_boot"]),
            set_at_wall=float(data["set_at_wall"]),
            warned=[int(x) for x in data.get("warned", [])],
            reached=bool(data.get("reached", False)),
        )


class StateStore:
    """Keeps the bedtime state in a file so a Decky restart doesn't clear it.

    The file is tagged with the kernel boot id and ignored (and deleted) after
    a reboot, so nothing carries over. /run is preferred because it is a tmpfs.
    """

    FILENAME = "bedtime-state.json"

    def __init__(self, directory: str, boot_id: Optional[str] = None):
        self.directory = directory
        self.path = os.path.join(directory, self.FILENAME)
        self.boot_id = boot_id or read_boot_id()

    def load(self) -> Optional[BedtimeState]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                state = BedtimeState.from_json(fh.read())
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError):
            self.clear()
            return None
        if state.boot_id != self.boot_id:
            self.clear()
            return None
        return state

    def save(self, state: BedtimeState) -> None:
        os.makedirs(self.directory, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(state.to_json())
        os.replace(tmp, self.path)

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass


def pick_state_dir(fallback: str) -> str:
    """Prefer a tmpfs under /run (gone after reboot), else the fallback dir."""
    candidate = "/run/decky-bedtime"
    try:
        os.makedirs(candidate, mode=0o700, exist_ok=True)
        if os.access(candidate, os.W_OK):
            return candidate
    except OSError:
        pass
    return fallback


# --------------------------------------------------------------------------
# Status payload shared by the web page and the Deck UI
# --------------------------------------------------------------------------

def format_remaining(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min"
    return "less than a minute"


def status_payload(state: Optional[BedtimeState], settings: dict[str, Any],
                   now_boot: Optional[float] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "set": state is not None,
        "bedtime": None,
        "deadline": None,
        "remainingSeconds": None,
        "remainingText": None,
        "reached": False,
        "defaultBedtime": settings.get("defaultBedtime", DEFAULT_SETTINGS["defaultBedtime"]),
    }
    if state is not None:
        rem = state.remaining(now_boot)
        payload.update(
            bedtime=state.bedtime,
            deadline=int(state.deadline_wall),
            remainingSeconds=max(0, int(rem)),
            remainingText=format_remaining(rem),
            reached=state.reached or rem <= 0,
        )
    return payload


# --------------------------------------------------------------------------
# Game process enforcement (fallback for the frontend's TerminateApp)
# --------------------------------------------------------------------------

def _read_cmdline(pid: int) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def _read_ppid(pid: int) -> Optional[int]:
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="replace") as fh:
            stat = fh.read()
    except OSError:
        return None
    # The command name (field 2) may contain spaces/parentheses; skip past it.
    try:
        rest = stat[stat.rindex(")") + 2:].split()
        return int(rest[1])
    except (ValueError, IndexError):
        return None


def _all_pids() -> list[int]:
    try:
        return [int(name) for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return []


def is_game_reaper(argv: list[str]) -> bool:
    """Steam starts every game (incl. non-Steam shortcuts) under `reaper SteamLaunch AppId=N`."""
    if not argv:
        return False
    if os.path.basename(argv[0]) != "reaper":
        return False
    return "SteamLaunch" in argv and any(a.startswith("AppId=") for a in argv)


def find_game_reapers() -> dict[int, Optional[str]]:
    found: dict[int, Optional[str]] = {}
    for pid in _all_pids():
        argv = _read_cmdline(pid)
        if is_game_reaper(argv):
            appid = next((a.split("=", 1)[1] for a in argv if a.startswith("AppId=")), None)
            found[pid] = appid
    return found


def process_tree(root: int) -> list[int]:
    children: dict[int, list[int]] = {}
    for pid in _all_pids():
        ppid = _read_ppid(pid)
        if ppid is not None:
            children.setdefault(ppid, []).append(pid)
    tree, todo = [], [root]
    while todo:
        pid = todo.pop()
        tree.append(pid)
        todo.extend(children.get(pid, []))
    return tree


def signal_game_processes(sig: int = signal.SIGTERM) -> list[dict[str, Any]]:
    """Send `sig` to every running game's process tree. Returns what was hit."""
    me = os.getpid()
    results = []
    for pid, appid in find_game_reapers().items():
        for target in reversed(process_tree(pid)):
            if target <= 1 or target == me:
                continue
            try:
                os.kill(target, sig)
            except OSError:
                pass
        results.append({"pid": pid, "appid": appid})
    return results
