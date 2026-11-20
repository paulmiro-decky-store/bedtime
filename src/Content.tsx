import { useEffect, useState } from "react";
import {
  ButtonItem,
  Field,
  Navigation,
  PanelSection,
  PanelSectionRow,
} from "@decky/ui";
import { getStatus, Status } from "./api";
import { SETTINGS_ROUTE } from "./constants";

export function useStatus(intervalMs = 5000): [Status | null, (s: Status) => void] {
  const [status, setStatus] = useState<Status | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      getStatus()
        .then((s) => alive && setStatus(s))
        .catch((err) => console.error("Bedtime: get_status failed", err));
    load();
    const timer = setInterval(load, intervalMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [intervalMs]);
  return [status, setStatus];
}

export function Content() {
  const [status] = useStatus();

  let headline = "Loading…";
  let detail: string | null = null;
  if (status) {
    if (!status.set) {
      headline = "No bedtime set";
      detail = "Set one from your phone.";
    } else if (status.reached) {
      headline = `Bedtime reached (${status.bedtime})`;
      detail = "Games are blocked until the device restarts.";
    } else {
      headline = `Bedtime ${status.bedtime}`;
      detail = `${status.remainingText} left. Can only be moved earlier until the device restarts.`;
    }
  }

  return (
    <>
      <PanelSection title="Status">
        <PanelSectionRow>
          <Field label={headline} description={detail} bottomSeparator="none" />
        </PanelSectionRow>
      </PanelSection>
      <PanelSection title="Web page">
        <PanelSectionRow>
          <Field
            label={status?.url ?? (status?.serverError ? "Not running" : "…")}
            description={
              status?.serverError ??
              "Open this address on a phone in the same network to set the bedtime."
            }
            bottomSeparator="none"
          />
        </PanelSectionRow>
      </PanelSection>
      <PanelSection>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => {
              Navigation.CloseSideMenus();
              Navigation.Navigate(SETTINGS_ROUTE);
            }}
          >
            Settings
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}
