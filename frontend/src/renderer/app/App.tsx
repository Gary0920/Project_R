import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../shared/api/client";
import type { CurrentUserResponse } from "../shared/api/types";
import {
  authTokenAtom,
  clearAuthAtom,
  isAuthenticatedAtom,
  refreshCurrentUserAtom,
} from "../features/auth/state";
import { serverUrlAtom } from "../shared/state/server";
import { AppShell } from "./AppShell";
import { AppPage } from "../pages/AppPage";
import { LoginPage } from "../pages/LoginPage";
import { OnboardingPage } from "../pages/OnboardingPage";

function getRoute() {
  const hash = window.location.hash || "#/login";
  return hash.replace("#", "");
}

const ONBOARDING_DONE_KEY = "project-r:onboarding-complete";

function isOnboardingComplete() {
  return localStorage.getItem(ONBOARDING_DONE_KEY) === "true";
}

function applyStoredTheme() {
  try {
    const prefs = JSON.parse(localStorage.getItem("project-r:settings-preferences") ?? "{}") as { theme?: string };
    const theme = prefs.theme ?? "system";
    const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
    const resolved = theme === "system" ? (prefersDark ? "dark" : "light") : theme;
    document.documentElement.dataset.theme = resolved === "dark" ? "dark" : "light";
  } catch {
    document.documentElement.dataset.theme = "light";
  }
}

function RouteView() {
  const [route, setRoute] = useState(getRoute());
  const [onboardingComplete, setOnboardingComplete] = useState(isOnboardingComplete);
  const token = useAtomValue(authTokenAtom);
  const isAuthenticated = useAtomValue(isAuthenticatedAtom);
  const serverUrl = useAtomValue(serverUrlAtom);
  const clearAuth = useSetAtom(clearAuthAtom);
  const refreshCurrentUser = useSetAtom(refreshCurrentUserAtom);

  useEffect(() => {
    applyStoredTheme();
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener?.("change", applyStoredTheme);
    return () => media?.removeEventListener?.("change", applyStoredTheme);
  }, []);

  useEffect(() => {
    const onHashChange = () => setRoute(getRoute());
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) {
      window.location.hash = isOnboardingComplete() ? "#/login" : "#/onboarding";
    }
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (!token) {
      return;
    }

    let isMounted = true;
    apiRequest<CurrentUserResponse>(
      {
        baseUrl: serverUrl,
        token,
        onUnauthorized: clearAuth,
      },
      "/auth/me",
    )
      .then((user) => {
        if (isMounted) {
          refreshCurrentUser(user);
        }
      })
      .catch((error: unknown) => {
        if (!isMounted) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          clearAuth();
          window.location.hash = "#/login";
        }
      });

    return () => {
      isMounted = false;
    };
  }, [clearAuth, refreshCurrentUser, serverUrl, token]);

  if (route === "/app") {
    if (!isAuthenticated) {
      return <LoginPage />;
    }
    return <AppPage />;
  }
  if (route === "/settings") {
    window.location.hash = "#/app";
    return null;
  }
  if (route === "/onboarding") {
    return <OnboardingPage onComplete={() => {
      localStorage.setItem(ONBOARDING_DONE_KEY, "true");
      setOnboardingComplete(true);
      window.location.hash = "#/login";
    }} />;
  }
  if (!onboardingComplete && !isAuthenticated) {
    window.location.hash = "#/onboarding";
    return <OnboardingPage onComplete={() => {
      localStorage.setItem(ONBOARDING_DONE_KEY, "true");
      setOnboardingComplete(true);
      window.location.hash = "#/login";
    }} />;
  }
  return <LoginPage />;
}

export function App() {
  return (
    <AppShell>
      <RouteView />
    </AppShell>
  );
}
