"""Minimal stand-in for Decky's `decky` module so main.py can run in tests."""
import logging
import os
import tempfile

_root = tempfile.mkdtemp(prefix="decky-bedtime-test-")
DECKY_PLUGIN_SETTINGS_DIR = os.path.join(_root, "settings")
DECKY_PLUGIN_RUNTIME_DIR = os.path.join(_root, "runtime")
DECKY_PLUGIN_LOG_DIR = os.path.join(_root, "logs")

logger = logging.getLogger("decky-bedtime-test")
events: list = []


async def emit(event, *args):
    events.append((event, *args))
