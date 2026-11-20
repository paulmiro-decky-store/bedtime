import { staticClasses } from "@decky/ui";
import {
  addEventListener,
  definePlugin,
  removeEventListener,
  routerHook,
  toaster,
} from "@decky/api";
import { FaMoon } from "react-icons/fa";
import { getStatus, Status } from "./api";
import { Content } from "./Content";
import { SettingsPage } from "./SettingsPage";
import { SETTINGS_ROUTE } from "./constants";
import { setBlocking, teardown } from "./enforce";

const TITLE = "Bedtime";

export default definePlugin(() => {
  routerHook.addRoute(SETTINGS_ROUTE, SettingsPage, { exact: true });

  const onSet = (s: Status) =>
    toaster.toast({
      title: TITLE,
      body: `Bedtime set to ${s.bedtime} (${s.remainingText} left).`,
      duration: 8000,
    });

  const onWarning = (minutes: number) =>
    toaster.toast({
      title: TITLE,
      body:
        minutes === 1
          ? "1 minute until bedtime. The game will be closed — save now!"
          : `${minutes} minutes until bedtime.`,
      duration: minutes === 1 ? 15000 : 8000,
      critical: minutes === 1,
    });

  const onReached = () => {
    toaster.toast({
      title: TITLE,
      body: "It's bedtime. Closing the game.",
      duration: 10000,
      critical: true,
    });
    setBlocking(true);
  };

  addEventListener<[Status]>("bedtime_set", onSet);
  addEventListener<[number]>("bedtime_warning", onWarning);
  addEventListener<[]>("bedtime_reached", onReached);

  // Catch up after a reload and re-assert blocking in case an event was missed.
  const poll = async () => {
    try {
      const s = await getStatus();
      setBlocking(s.reached);
    } catch (err) {
      console.error("Bedtime: status poll failed", err);
    }
  };
  void poll();
  const timer = setInterval(poll, 5000);

  return {
    name: TITLE,
    titleView: <div className={staticClasses.Title}>{TITLE}</div>,
    content: <Content />,
    icon: <FaMoon />,
    onDismount() {
      clearInterval(timer);
      removeEventListener("bedtime_set", onSet);
      removeEventListener("bedtime_warning", onWarning);
      removeEventListener("bedtime_reached", onReached);
      routerHook.removeRoute(SETTINGS_ROUTE);
      teardown();
    },
  };
});
