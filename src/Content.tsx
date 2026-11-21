import { useEffect, useState } from "react";
import {
  ButtonItem,
  ConfirmModal,
  Field,
  Navigation,
  PanelSection,
  PanelSectionRow,
  showModal,
  SliderField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { getStatus, setBedtimeIn, Status } from "./api";
import { SETTINGS_ROUTE } from "./constants";

const STEP = 15;
const MIN_MINUTES = 15;
const MAX_MINUTES = 6 * 60;

const pad = (n: number) => String(n).padStart(2, "0");

function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** Clock time `minutes` from now, rounded down to the minute like the backend. */
function clockIn(minutes: number): string {
  const t = new Date(Date.now() + minutes * 60000);
  return `${pad(t.getHours())}:${pad(t.getMinutes())}`;
}

function minutesUntil(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  const now = new Date();
  const t = new Date(now);
  t.setHours(h, m, 0, 0);
  if (t <= now) t.setDate(t.getDate() + 1);
  return (t.getTime() - now.getTime()) / 60000;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

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

/** Largest slider value that still gives a bedtime earlier than the current one. */
function sliderMax(status: Status): number {
  if (!status.set) return MAX_MINUTES;
  // Keep a margin: the backend rounds down to the minute and needs "strictly earlier".
  const usable = ((status.remainingSeconds ?? 0) - 90) / 60;
  return Math.min(MAX_MINUTES, Math.floor(usable / STEP) * STEP);
}

function BedtimeSlider({ status, onChanged }: { status: Status; onChanged: (s: Status) => void }) {
  const max = sliderMax(status);
  const key = status.set ? `set:${status.bedtime}` : "unset";
  const initial = () =>
    status.set
      ? max
      : clamp(Math.round(minutesUntil(status.defaultBedtime) / STEP) * STEP, MIN_MINUTES, MAX_MINUTES);
  const [value, setValue] = useState(initial);
  const [shownFor, setShownFor] = useState(key);
  const [, setTick] = useState(0);

  // Re-initialise when the bedtime changes; keep the value valid as time passes.
  useEffect(() => {
    if (shownFor !== key) {
      setShownFor(key);
      setValue(initial());
    } else if (value > max) {
      setValue(max);
    }
  }, [key, max]);

  // Refresh the "→ HH:MM" preview while the menu is open.
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 20000);
    return () => clearInterval(t);
  }, []);

  if (max < MIN_MINUTES) {
    return (
      <PanelSectionRow>
        <Field
          label="Move bedtime earlier"
          description="Less than 15 minutes left. Use the web page to move it earlier."
          bottomSeparator="none"
        />
      </PanelSectionRow>
    );
  }

  const v = clamp(value, MIN_MINUTES, max);
  const verb = status.set ? "Move bedtime earlier" : "Set bedtime";

  const confirm = () => {
    const at = clockIn(v);
    showModal(
      <ConfirmModal
        strTitle={`${verb} to ${at}?`}
        strDescription={
          `Games will be closed in ${formatDuration(v)}, at ${at}, and blocked until the device restarts. ` +
          "After this, the bedtime can only be moved earlier."
        }
        strOKButtonText={verb}
        onOK={async () => {
          try {
            onChanged(await setBedtimeIn(v));
          } catch (err) {
            toaster.toast({ title: "Bedtime", body: `${err}`.replace(/^Error: /, "") });
          }
        }}
      />,
    );
  };

  return (
    <>
      <PanelSectionRow>
        <SliderField
          label={status.set ? "Stop playing earlier, in" : "Stop playing in"}
          description={`${formatDuration(v)} → ${clockIn(v)}`}
          value={v}
          min={MIN_MINUTES}
          max={max}
          step={STEP}
          validValues="steps"
          onChange={setValue}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={confirm}>
          {verb}
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}

export function Content() {
  const [status, setStatus] = useStatus();

  let headline = "Loading…";
  let detail: string | null = null;
  if (status) {
    if (!status.set) {
      headline = "No bedtime set";
      detail = "Set one below or from your phone.";
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
        {status && !status.reached && <BedtimeSlider status={status} onChanged={setStatus} />}
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
