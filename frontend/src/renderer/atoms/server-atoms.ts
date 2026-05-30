import { atom } from "jotai";

import { DEFAULT_API_BASE_URL } from "../constants/app";

const SERVER_URL_STORAGE_KEY = "project-r:server-url";

function readStoredServerUrl() {
  return window.localStorage.getItem(SERVER_URL_STORAGE_KEY) || DEFAULT_API_BASE_URL;
}

export const serverUrlAtom = atom(readStoredServerUrl());

export const setServerUrlAtom = atom(null, (_get, set, value: string) => {
  const normalized = value.trim().replace(/\/$/, "");
  window.localStorage.setItem(SERVER_URL_STORAGE_KEY, normalized);
  set(serverUrlAtom, normalized);
});
