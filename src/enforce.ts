// Closes running games and blocks new launches once bedtime is reached.
// The backend additionally terminates game processes as a fallback.
import { replacePatch, callOriginal, Router } from "@decky/ui";
import { toaster } from "@decky/api";

type Unpatch = { unpatch: () => void };
type Unregisterable = { unregister: () => void };

let blocking = false;
let runGamePatch: Unpatch | null = null;
let patchedFn: unknown = null;
let actionHook: Unregisterable | null = null;
let lastBlockedToast = 0;

function apps(): any {
  return (globalThis as any).SteamClient?.Apps ?? null;
}

function toastBlocked(): void {
  const now = Date.now();
  if (now - lastBlockedToast < 3000) return;
  lastBlockedToast = now;
  toaster.toast({
    title: "Bedtime",
    body: "It's past bedtime. Games are blocked until the device restarts.",
    duration: 5000,
  });
}

function ensureHooks(): void {
  const a = apps();
  if (!a) return;

  // Steam may replace the method object; re-patch if our patch is gone.
  if (a.RunGame && a.RunGame !== patchedFn) {
    try {
      runGamePatch?.unpatch();
    } catch {
      /* ignore */
    }
    try {
      runGamePatch = replacePatch(a, "RunGame", () => {
        if (!blocking) return callOriginal;
        toastBlocked();
        return undefined;
      }) as Unpatch;
      patchedFn = a.RunGame;
    } catch (err) {
      console.error("Bedtime: failed to patch RunGame", err);
    }
  }

  if (!actionHook && a.RegisterForGameActionStart) {
    try {
      actionHook = a.RegisterForGameActionStart(
        (actionId: number, appId: string, action: string) => {
          if (!blocking || !/launch/i.test(String(action))) return;
          try {
            a.CancelGameAction?.(actionId);
            a.TerminateApp?.(String(appId), false);
          } catch (err) {
            console.error("Bedtime: cancelling launch failed", err);
          }
          toastBlocked();
        },
      );
    } catch (err) {
      console.error("Bedtime: RegisterForGameActionStart failed", err);
    }
  }
}

export function closeRunningGames(): void {
  const a = apps();
  for (const app of Router.RunningApps ?? []) {
    try {
      a?.TerminateApp?.(String(app.appid), false);
    } catch (err) {
      console.error("Bedtime: TerminateApp failed", err);
    }
  }
}

export function setBlocking(value: boolean): void {
  ensureHooks();
  blocking = value;
  if (value) closeRunningGames();
}

export function isBlocking(): boolean {
  return blocking;
}

export function teardown(): void {
  blocking = false;
  try {
    runGamePatch?.unpatch();
  } catch {
    /* ignore */
  }
  runGamePatch = null;
  patchedFn = null;
  try {
    actionHook?.unregister();
  } catch {
    /* ignore */
  }
  actionHook = null;
}
