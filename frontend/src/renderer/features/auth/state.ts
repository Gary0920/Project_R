import { atom } from "jotai";

import type { CurrentUserResponse, LoginResponse } from "../../shared/api/types";

const AUTH_TOKEN_STORAGE_KEY = "project-r:auth-token";
const AUTH_USER_STORAGE_KEY = "project-r:auth-user";

export type AuthUser = CurrentUserResponse;

function readStoredToken() {
  return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
}

function readStoredUser(): AuthUser | null {
  const raw = window.localStorage.getItem(AUTH_USER_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    window.localStorage.removeItem(AUTH_USER_STORAGE_KEY);
    return null;
  }
}

export const authTokenAtom = atom<string | null>(readStoredToken());
export const currentUserAtom = atom<AuthUser | null>(readStoredUser());

export const isAuthenticatedAtom = atom((get) => Boolean(get(authTokenAtom) && get(currentUserAtom)));

export const setAuthAtom = atom(null, (_get, set, payload: LoginResponse) => {
  const user: AuthUser = {
    user_id: payload.user_id,
    username: payload.username,
    role: payload.role,
    nickname: payload.nickname,
    avatar: payload.avatar,
    work_group: payload.work_group,
    last_login_at: payload.last_login_at,
  };

  window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, payload.token);
  window.localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user));
  set(authTokenAtom, payload.token);
  set(currentUserAtom, user);
});

export const refreshCurrentUserAtom = atom(
  null,
  (get, set, user: AuthUser) => {
    window.localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user));
    set(currentUserAtom, user);
    return get(authTokenAtom);
  },
);

export const clearAuthAtom = atom(null, (_get, set) => {
  window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  window.localStorage.removeItem(AUTH_USER_STORAGE_KEY);
  set(authTokenAtom, null);
  set(currentUserAtom, null);
});
