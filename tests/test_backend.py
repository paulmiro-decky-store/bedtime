"""Runs main.Plugin against a fake `decky` module and drives the web API."""
import asyncio
import json
import os
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import fake_decky  # noqa: E402

sys.modules["decky"] = fake_decky

import main  # noqa: E402  (adds py_modules to sys.path)
import bedtime_core  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def in_hours(hours: float) -> str:
    return (datetime.now() + timedelta(hours=hours)).strftime("%H:%M")


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        main.MANAGED_CONFIG = os.path.join(self.tmp.name, "managed.json")
        main.pick_state_dir = lambda fallback: os.path.join(self.tmp.name, "state")
        self.port = free_port()
        os.makedirs(fake_decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
        with open(os.path.join(fake_decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json"), "w") as fh:
            json.dump({"listenAddress": "127.0.0.1", "port": self.port, "defaultBedtime": "20:15"}, fh)
        fake_decky.events.clear()
        self.plugin = main.Plugin()
        await self.plugin._main()
        self.base = f"http://127.0.0.1:{self.port}"

    async def asyncTearDown(self):
        await self.plugin._unload()
        self.tmp.cleanup()

    async def get(self, path):
        return await asyncio.to_thread(http, "GET", self.base + path)

    async def post(self, path, body):
        return await asyncio.to_thread(http, "POST", self.base + path, body)

    async def test_set_then_only_earlier(self):
        code, page = await self.get("/")
        self.assertEqual(code, 200)
        self.assertIn('type="time"', page)

        code, body = await self.get("/api/status")
        self.assertEqual(json.loads(body)["defaultBedtime"], "20:15")

        code, body = await self.post("/api/bedtime", {"time": "25:00"})
        self.assertEqual(code, 400)

        t3, t2, t1 = in_hours(3), in_hours(2), in_hours(1)
        code, body = await self.post("/api/bedtime", {"time": t2})
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(body)["bedtime"], t2)
        self.assertEqual(fake_decky.events[-1][0], "bedtime_set")
        self.assertFalse(fake_decky.events[-1][1]["changed"])

        # Later or equal: rejected.
        for later in (t3, t2):
            code, body = await self.post("/api/bedtime", {"time": later})
            self.assertEqual(code, 409, later)
            self.assertIn("earlier", json.loads(body)["error"])

        # Earlier: accepted.
        code, body = await self.post("/api/bedtime", {"time": t1})
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(body)["bedtime"], t1)
        self.assertTrue(fake_decky.events[-1][1]["changed"])

        # Can't go back to the later time after moving earlier.
        code, _ = await self.post("/api/bedtime", {"time": t2})
        self.assertEqual(code, 409)

        # Survives a plugin reload within the same boot.
        await self.plugin._unload()
        self.plugin = main.Plugin()
        await self.plugin._main()
        status = await self.plugin.get_status()
        self.assertEqual(status["bedtime"], t1)

    async def test_no_change_after_bedtime_reached(self):
        await self.post("/api/bedtime", {"time": in_hours(2)})
        self.plugin.state.deadline_boot = bedtime_core.boottime() - 1
        await self.plugin._tick()
        code, body = await self.post("/api/bedtime", {"time": in_hours(1)})
        self.assertEqual(code, 409)
        self.assertIn("reached", json.loads(body)["error"])

    async def test_warnings_and_reached(self):
        await self.post("/api/bedtime", {"time": in_hours(2)})
        st = self.plugin.state
        # Pretend 14 minutes are left.
        st.deadline_boot = bedtime_core.boottime() + 14 * 60
        await self.plugin._tick()
        self.assertIn(("bedtime_warning", 15), fake_decky.events)
        st.deadline_boot = bedtime_core.boottime() - 1
        await self.plugin._tick()
        self.assertIn(("bedtime_reached",), fake_decky.events)
        # The 5/1 minute warnings are not sent after bedtime.
        self.assertNotIn(("bedtime_warning", 5), fake_decky.events)
        code, body = await self.get("/api/status")
        self.assertTrue(json.loads(body)["reached"])

    async def test_settings_and_managed(self):
        new_port = free_port()
        status = await self.plugin.save_settings({"port": new_port, "defaultBedtime": "19:45"})
        self.assertEqual(status["settings"]["defaultBedtime"], "19:45")
        self.assertEqual(self.plugin.server.port, new_port)
        code, _ = await asyncio.to_thread(http, "GET", f"http://127.0.0.1:{new_port}/api/status")
        self.assertEqual(code, 200)

        managed_port = free_port()
        with open(main.MANAGED_CONFIG, "w") as fh:
            json.dump({"port": managed_port, "listenAddress": None}, fh)
        status = await self.plugin.save_settings({"port": 1234})
        self.assertEqual(status["managed"], ["port"])
        self.assertEqual(status["settings"]["port"], managed_port)
        self.assertEqual(self.plugin.server.port, managed_port)


if __name__ == "__main__":
    unittest.main()
