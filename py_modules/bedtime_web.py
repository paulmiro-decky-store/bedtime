"""Small phone-oriented web page for setting the bedtime."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiohttp import web

StatusFn = Callable[[], dict[str, Any]]
SetFn = Callable[[str], Awaitable[dict[str, Any]]]


class BedtimeAlreadySet(Exception):
    pass


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark light">
<title>Bedtime</title>
<style>
  :root { --bg:#10141c; --fg:#eef1f6; --muted:#9aa4b5; --card:#1b2230; --accent:#5aa9ff; --err:#ff6b6b; }
  @media (prefers-color-scheme: light) {
    :root { --bg:#f3f5f9; --fg:#141821; --muted:#5b6475; --card:#ffffff; --accent:#1a6fd6; --err:#c62828; }
  }
  * { box-sizing: border-box; }
  html, body { margin:0; background:var(--bg); color:var(--fg);
    font: 18px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { min-height:100dvh; display:flex; flex-direction:column; justify-content:center;
    gap:20px; padding:24px 16px calc(24px + env(safe-area-inset-bottom)); max-width:480px; margin:0 auto; }
  h1 { font-size:1.6rem; margin:0; text-align:center; }
  .card { background:var(--card); border-radius:18px; padding:20px; display:flex; flex-direction:column; gap:16px; }
  label { color:var(--muted); font-size:.95rem; }
  input[type=time] { width:100%; font-size:2.6rem; padding:12px; border-radius:12px;
    border:2px solid var(--muted); background:transparent; color:var(--fg); text-align:center; }
  button { width:100%; font-size:1.25rem; font-weight:600; padding:16px; border:0; border-radius:12px;
    background:var(--accent); color:#fff; }
  button:disabled { opacity:.5; }
  .hint { color:var(--muted); text-align:center; min-height:1.4em; margin:0; }
  .big { font-size:3rem; font-weight:700; text-align:center; margin:0; }
  .err { color:var(--err); text-align:center; margin:0; }
  [hidden] { display:none !important; }
</style>
</head>
<body>
<main>
  <h1>Bedtime</h1>

  <form id="form" class="card" hidden>
    <label for="time">Stop playing at</label>
    <input id="time" type="time" required>
    <p id="preview" class="hint"></p>
    <button id="submit" type="submit">Set bedtime</button>
    <p class="hint">Can't be changed until the device restarts.</p>
  </form>

  <section id="locked" class="card" hidden>
    <p class="hint" id="locked-label">Bedtime</p>
    <p class="big" id="locked-time"></p>
    <p class="hint" id="locked-left"></p>
  </section>

  <p id="error" class="err" hidden></p>
</main>
<script>
const $ = (id) => document.getElementById(id);
let defaultsApplied = false;

function untilText(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  const now = new Date();
  const t = new Date(now); t.setHours(h, m, 0, 0);
  if (t <= now) t.setDate(t.getDate() + 1);
  const mins = Math.round((t - now) / 60000);
  const hh = Math.floor(mins / 60), mm = mins % 60;
  const span = hh ? `${hh} h ${mm} min` : `${mm} min`;
  const day = t.getDate() !== now.getDate() ? " (tomorrow)" : "";
  return `In ${span}${day}`;
}

function render(s) {
  $("form").hidden = s.set;
  $("locked").hidden = !s.set;
  if (s.set) {
    $("locked-time").textContent = s.bedtime;
    $("locked-label").textContent = s.reached ? "Bedtime reached" : "Bedtime set for";
    $("locked-left").textContent = s.reached
      ? "Games are blocked until the device restarts."
      : `${s.remainingText} left. Locked until the device restarts.`;
  } else if (!defaultsApplied) {
    $("time").value = s.defaultBedtime;
    defaultsApplied = true;
    updatePreview();
  }
}

function updatePreview() {
  const v = $("time").value;
  $("preview").textContent = v ? untilText(v) : "";
}

function showError(msg) { $("error").textContent = msg; $("error").hidden = !msg; }

async function refresh() {
  try {
    const r = await fetch("api/status", { cache: "no-store" });
    render(await r.json());
    showError("");
  } catch (e) { showError("Can't reach the device."); }
}

$("time").addEventListener("input", updatePreview);
$("form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const time = $("time").value;
  if (!time) return;
  if (!confirm(`Set bedtime to ${time}? ${untilText(time)}.\\nThis can't be changed until the device restarts.`)) return;
  $("submit").disabled = true;
  try {
    const r = await fetch("api/bedtime", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ time }),
    });
    const body = await r.json();
    if (!r.ok) showError(body.error || "Failed to set bedtime.");
    else { showError(""); render(body); }
  } catch (e) { showError("Can't reach the device."); }
  $("submit").disabled = false;
});

refresh();
setInterval(refresh, 15000);
setInterval(updatePreview, 30000);
</script>
</body>
</html>
"""


def make_app(get_status: StatusFn, set_bedtime: SetFn) -> web.Application:
    async def index(_request: web.Request) -> web.Response:
        return web.Response(text=PAGE, content_type="text/html",
                            headers={"Cache-Control": "no-store"})

    async def status(_request: web.Request) -> web.Response:
        return web.json_response(get_status(), headers={"Cache-Control": "no-store"})

    async def bedtime(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid request."}, status=400)
        value = data.get("time") if isinstance(data, dict) else None
        try:
            result = await set_bedtime(value)
        except BedtimeAlreadySet:
            return web.json_response(
                {"error": "Bedtime is already set and locked until the device restarts."},
                status=409)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(result)

    app = web.Application(client_max_size=4096)
    app.router.add_get("/", index)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/bedtime", bedtime)
    return app


class WebServer:
    def __init__(self, app_factory: Callable[[], web.Application]):
        self._factory = app_factory
        self._runner: web.AppRunner | None = None
        self.address: str | None = None
        self.port: int | None = None
        self.error: str | None = None

    async def start(self, address: str, port: int) -> None:
        await self.stop()
        self.address, self.port, self.error = address, port, None
        runner = web.AppRunner(self._factory(), access_log=None)
        await runner.setup()
        try:
            site = web.TCPSite(runner, host=address, port=port, reuse_address=True)
            await site.start()
        except Exception as exc:
            await runner.cleanup()
            self.error = f"Could not listen on {address}:{port}: {exc}"
            raise
        self._runner = runner

    async def stop(self) -> None:
        if self._runner is not None:
            runner, self._runner = self._runner, None
            await runner.cleanup()

    @property
    def running(self) -> bool:
        return self._runner is not None
