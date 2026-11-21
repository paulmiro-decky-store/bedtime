# Bedtime (Decky Loader plugin)

Set an end-of-play time for a Steam Deck (or any Decky Loader device) from a phone.

- The device serves a small web page (default `http://<device-ip>:19114/`) with one time picker and a **Set bedtime** button (**Move earlier** once a bedtime is set).
- Once set, the bedtime can only be **moved earlier** until the next reboot. The web page refuses a later time, and so does the device itself (HTTP 409), so calling the API directly doesn't get around it. After bedtime is reached it can't be changed at all.
- Steam toasts appear **15, 5 and 1 minute** before bedtime.
- At bedtime the running game is closed and **game launches are blocked until the device restarts**.
- Nothing carries over a reboot. The bedtime is kept in the plugin's runtime directory, tagged with the kernel boot ID, so a Decky restart keeps it but a reboot clears it.

The Quick Access menu shows the current bedtime, the time left and the web page's address. It can also set the bedtime: a **Stop playing in…** slider (15 min to 6 h, in 15-minute steps) shows the resulting clock time, e.g. `1 h 30 min → 22:45`, and **Set bedtime** asks for confirmation. Once a bedtime is set, the slider only goes up to just before it and the button says **Move bedtime earlier**. The same rules as on the web page apply, enforced by the backend.

Its **Settings** screen has:

- **Default bedtime**: only pre-fills the picker on the web page. It is never applied on its own.
- **Listen address** and **port** for the web page.

## How enforcement works

- **Frontend:** at bedtime it calls Steam's `TerminateApp` for running games. It also patches `SteamClient.Apps.RunGame` and cancels launch game actions while blocking. Every 5 seconds it re-checks with the backend.
- **Backend (fallback):** 20 seconds after bedtime it sends SIGTERM to the process tree of every Steam `reaper SteamLaunch AppId=…` process. Non-Steam shortcuts launch the same way. Anything still alive 15 seconds later gets SIGKILL. The check repeats every second until reboot.
- The countdown uses `CLOCK_BOOTTIME`. Changing the clock or time zone after setting the bedtime doesn't move it, and time spent suspended still counts.

The plugin uses the `_root` flag. It needs root to signal game processes owned by the Steam user (on Jovian-NixOS, Decky's backend user is not the Steam user).

## Limitations

- The web page has no login. Anyone on the network who opens it first can set the bedtime. Use `listenAddress` and the firewall to limit who can reach it.
- This is a guard rail, not tamper-proof parental control. Rebooting clears the bedtime by design. Uninstalling the plugin, Desktop Mode or another session can get around it.
- Launch blocking relies on undocumented Steam client internals, which a Steam update may change. The backend process killing still applies if that happens.
- Notifications are Decky toasts, which use Steam's toast UI. They only show while Game Mode (Steam) is running.

## Installation

The plugin is published for [decky-store-proxy](https://github.com/paulmiro/decky-store-proxy): each GitHub release carries the plugin zip and a `decky-store.json`. Add this repository as a source in the proxy's configuration:

```toml
[sources.github]
repos = ["paulmiro/decky-bedtime"]
```

If you add `users = ["paulmiro"]` instead, the repository needs the `decky-plugin` topic (or another topic from the proxy's `topics` setting).

"Bedtime" then shows up in Decky's store next to the official plugins, and updates arrive like any other store plugin. It works on SteamOS and on Jovian-NixOS with the default `jovian.decky-loader` settings. It needs only the Python standard library and `aiohttp` (which ships with Decky), and calls no external programs.

The web page has to be reachable from the phone. SteamOS has no firewall by default. On NixOS, open the port yourself:

```nix
networking.firewall.allowedTCPPorts = [ 19114 ];
```

### Without the proxy

Download `decky-bedtime-decky-plugin.zip` from a release and use **Decky → Settings → Developer → Install Plugin from ZIP**.

## Releasing

`.github/workflows/release.yml` builds the plugin and runs the proxy's [`package-plugin`](https://github.com/paulmiro/decky-store-proxy/blob/main/docs/plugin-development.md) action, which checks NixOS compatibility, creates the release and attaches the zip and `decky-store.json`. To release:

1. Bump `version` in `package.json` (strict SemVer, no `v`) and commit.
2. Either tag and push (`git tag vX.Y.Z && git push origin main vX.Y.Z`), or open the **Release** workflow in the Actions tab and press **Run workflow** on `main`. The manual run tags the current commit with `v` + the version and releases it; it fails if that tag already exists.

The tag must be `v` + the `package.json` version, or the workflow fails. Never change `name` in `plugin.json`: Decky uses it to match the installed plugin to the store entry.

## Development

```sh
nix develop
pnpm install
pnpm run build                         # frontend -> dist/index.js
python3 -m unittest discover -s tests  # backend tests (needs aiohttp)
nix flake check                        # build + backend tests on python3 and python313
```

The backend tests run `main.py` against a fake `decky` module and use the real web server. The flake (built with [flake-parts](https://flake.parts)) also provides `packages.<system>.decky-bedtime`, the plugin directory as Decky installs it.

## License

[The Unlicense](LICENSE) (public domain).
