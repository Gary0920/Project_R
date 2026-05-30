import { useEffect, useState } from "react";
import { WindowControls } from "./WindowControls";

export type AppShellProps = {
  children: React.ReactNode;
};

function getRoute() {
  const hash = window.location.hash || "#/login";
  return hash.replace("#", "");
}

export function AppShell({ children }: AppShellProps) {
  const [route, setRoute] = useState(getRoute());

  useEffect(() => {
    const onHashChange = () => setRoute(getRoute());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const isAuthRoute = route === "/login" || route === "/onboarding";

  if (route === "/app") {
    return <>{children}</>;
  }

  return (
    <div className={`shell-window-fallback ${isAuthRoute ? "is-auth-route" : ""}`}>
      <div className="fallback-window-strip">
        <span className="fallback-window-title">Project_R</span>
        <WindowControls />
      </div>
      <div className={isAuthRoute ? "shell-auth" : "shell-page"}>{children}</div>
    </div>
  );
}
