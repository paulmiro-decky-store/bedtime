# Bedtime (Decky Loader plugin)

Set an end-of-play time for a Steam Deck (or any Decky Loader device) from a phone.

- The device serves a small web page (default `http://<device-ip>:19114/`) with one time picker and a **Set bedtime** button (**Move earlier** once a bedtime is set).
- Once set, the bedtime can only be **moved earlier** until the next reboot. The web page refuses a later time, and so does the device itself (HTTP 409), so calling the API directly doesn't get around it. After bedtime is reached it can't be changed at all.
- Steam toasts appear **15, 5 and 1 minute** before bedtime.
- At bedtime the running game is closed and **game launches are blocked until the device restarts**.
- Nothing carries over a reboot. The bedtime is kept in `/run` and tagged with the kernel boot ID, so a Decky restart keeps it but a reboot clears it.

The Quick Access menu shows the current bedtime, the time left and the web page's address. Its **Settings** screen has:

- **Default bedtime**: only pre-fills the picker on the web page. It is never applied on its own.
- **Listen address** and **port** for the web page. These are read-only when the NixOS module sets them.

The bedtime can't be set on the device itself, because `@decky/ui` has no time-picker component.

## How enforcement works

- **Frontend:** at bedtime it calls Steam's `TerminateApp` for running games. It also patches `SteamClient.Apps.RunGame` and cancels launch game actions while blocking. Every 5 seconds it re-checks with the backend.
- **Backend (fallback):** 20 seconds after bedtime it sends SIGTERM to the process tree of every Steam `reaper SteamLaunch AppId=…` process. Non-Steam shortcuts launch the same way. Anything still alive 15 seconds later gets SIGKILL. The check repeats every second until reboot.
- The countdown uses `CLOCK_BOOTTIME`. Changing the clock or time zone after setting the bedtime doesn't move it, and time spent suspended still counts.

The plugin uses the `_root` flag. It needs root to signal game processes owned by the Steam user and to write to `/run`.

## Limitations

- The web page has no login. Anyone on the network who opens it first can set the bedtime. Use `listenAddress` and the firewall to limit who can reach it.
- This is a guard rail, not tamper-proof parental control. Rebooting clears the bedtime by design. Uninstalling the plugin, Desktop Mode or another session can get around it.
- Launch blocking relies on undocumented Steam client internals, which a Steam update may change. The backend process killing still applies if that happens.
- Notifications are Decky toasts, which use Steam's toast UI. They only show while Game Mode (Steam) is running.

## NixOS / Jovian-NixOS

```nix
{
  inputs = {
    nixpkgs.url = "https://channels.nixos.org/nixos-unstable/nixexprs.tar.xz";
    jovian.url = "github:Jovian-Experiments/Jovian-NixOS";
    jovian.inputs.nixpkgs.follows = "nixpkgs";
    decky-bedtime.url = "github:paulmiro/decky-bedtime";
    decky-bedtime.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { nixpkgs, jovian, decky-bedtime, ... }: {
    nixosConfigurations.deck = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        jovian.nixosModules.default
        decky-bedtime.nixosModules.default
        {
          jovian.decky-loader.enable = true;
          jovian.decky-loader.bedtime = {
            enable = true;
            # Optional. When set, these are read-only in the plugin settings.
            # listenAddress = "0.0.0.0";
            port = 19114;
            openFirewall = true; # only allowed when `port` is set
          };
        }
      ];
    };
  };
}
```

Options under `jovian.decky-loader.bedtime`:

| Option | Default | Description |
| --- | --- | --- |
| `enable` | `false` | Install the plugin into `${jovian.decky-loader.stateDir}/plugins/decky-bedtime`. Also turns on `jovian.decky-loader.enable` by default. |
| `package` | this flake's package | Plugin package. |
| `listenAddress` | `null` | When set, fixes the listen address and makes it read-only on the device. |
| `port` | `null` | When set, fixes the port and makes it read-only on the device. |
| `openFirewall` | `false` | Open `port` in the firewall. There's an assertion that `port` is set. |

The plugin is copied into Decky's plugin directory in `decky-loader.service`'s `preStart`. Decky restarts when the package or the fixed address/port change.

The flake also provides `packages.<system>.decky-bedtime`, `overlays.default` and a dev shell.

## Manual install (SteamOS)

```sh
nix build .#decky-bedtime          # or: pnpm install && pnpm run build
```

Copy `main.py`, `plugin.json`, `package.json`, `LICENSE`, `py_modules/` and `dist/index.js` into `~/homebrew/plugins/decky-bedtime/`, then restart Decky.

## Development

```sh
nix develop
pnpm install
pnpm run build                         # frontend -> dist/index.js
python3 -m unittest discover -s tests  # backend tests (needs aiohttp)
nix flake check
```

The backend tests run `main.py` against a fake `decky` module and use the real web server.

## License

BSD-3-Clause
