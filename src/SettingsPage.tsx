import { useEffect, useState } from "react";
import {
  DialogBody,
  DialogButton,
  DialogControlsSection,
  DialogControlsSectionHeader,
  DropdownItem,
  Field,
  TextField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { saveSettings, Settings } from "./api";
import { useStatus } from "./Content";

const pad = (n: number) => String(n).padStart(2, "0");
const HOURS = Array.from({ length: 24 }, (_, h) => ({ data: h, label: pad(h) }));

function minuteOptions(current: number) {
  const values = new Set<number>(Array.from({ length: 12 }, (_, i) => i * 5));
  values.add(current);
  return [...values].sort((a, b) => a - b).map((m) => ({ data: m, label: pad(m) }));
}

export function SettingsPage() {
  const [status, setStatus] = useStatus(10000);
  const [address, setAddress] = useState("");
  const [port, setPort] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (status && !dirty) {
      setAddress(status.settings.listenAddress);
      setPort(String(status.settings.port));
    }
  }, [status, dirty]);

  if (!status) {
    return <div style={{ marginTop: "50px", padding: "16px" }}>Loading…</div>;
  }

  const [hour, minute] = status.settings.defaultBedtime.split(":").map(Number);

  const save = async (patch: Partial<Settings>) => {
    setSaving(true);
    try {
      const next = await saveSettings(patch);
      setStatus(next);
      return true;
    } catch (err) {
      toaster.toast({ title: "Bedtime", body: `Could not save: ${err}` });
      return false;
    } finally {
      setSaving(false);
    }
  };

  const setDefault = (h: number, m: number) => save({ defaultBedtime: `${pad(h)}:${pad(m)}` });

  const saveNetwork = async () => {
    if (await save({ listenAddress: address.trim(), port: Number(port) })) setDirty(false);
  };

  return (
    <div style={{ marginTop: "40px", height: "calc(100% - 40px)", overflowY: "auto" }}>
      <DialogBody>
        <DialogControlsSection>
          <DialogControlsSectionHeader>Default bedtime</DialogControlsSectionHeader>
          <Field
            description="Only pre-fills the time picker on the web page. It is never applied on its own."
            bottomSeparator="none"
          />
          <DropdownItem
            label="Hour"
            rgOptions={HOURS}
            selectedOption={hour}
            disabled={saving}
            onChange={(o) => setDefault(o.data, minute)}
          />
          <DropdownItem
            label="Minute"
            rgOptions={minuteOptions(minute)}
            selectedOption={minute}
            disabled={saving}
            onChange={(o) => setDefault(hour, o.data)}
          />
        </DialogControlsSection>

        <DialogControlsSection>
          <DialogControlsSectionHeader>Web server</DialogControlsSectionHeader>
          <TextField
            label="Listen address"
            description="0.0.0.0 listens on all interfaces."
            value={address}
            onChange={(e) => {
              setAddress(e.target.value);
              setDirty(true);
            }}
          />
          <TextField
            label="Port"
            value={port}
            mustBeNumeric
            rangeMin={1}
            rangeMax={65535}
            onChange={(e) => {
              setPort(e.target.value);
              setDirty(true);
            }}
          />
          <Field bottomSeparator="none">
            <DialogButton disabled={!dirty || saving} onClick={saveNetwork}>
              Save and restart web server
            </DialogButton>
          </Field>
          <Field
            label="Currently"
            description={status.serverError ?? status.url ?? "Not running"}
            bottomSeparator="none"
          />
        </DialogControlsSection>
      </DialogBody>
    </div>
  );
}
