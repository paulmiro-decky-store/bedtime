import { callable } from "@decky/api";

export interface Settings {
  defaultBedtime: string;
  listenAddress: string;
  port: number;
}

export interface Status {
  set: boolean;
  bedtime: string | null;
  deadline: number | null;
  remainingSeconds: number | null;
  remainingText: string | null;
  reached: boolean;
  defaultBedtime: string;
  url: string | null;
  serverError: string | null;
  settings: Settings;
  managed: (keyof Settings)[];
  now: string;
  changed?: boolean;
}

export const getStatus = callable<[], Status>("get_status");
export const saveSettings = callable<[patch: Partial<Settings>], Status>("save_settings");
