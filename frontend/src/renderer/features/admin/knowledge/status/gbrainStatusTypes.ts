export type GBrainOverallLevel = "critical" | "attention" | "ok" | "unknown";

export type GBrainSignalStatus = GBrainOverallLevel;

export type GBrainSignalCard = {
  id: "doctor" | "worker" | "jobs" | "quality";
  label: string;
  status: GBrainSignalStatus;
  value: string;
  detail: string;
};

export type GBrainWarningItem = {
  id: string;
  level: Exclude<GBrainOverallLevel, "ok">;
  title: string;
  detail: string;
  action: string;
};

export type GBrainMaintenanceEntry = {
  id: "refresh" | "maintenance-check" | "quality" | "citation-fixer" | "operations";
  label: string;
  detail: string;
  actionLabel?: string;
  kind?: "button" | "reference";
};

export type GBrainStatusDashboardView = {
  overall: {
    level: GBrainOverallLevel;
    label: string;
    summary: string;
    basis: string[];
    updatedAt: string;
  };
  signals: GBrainSignalCard[];
  warnings: GBrainWarningItem[];
  entries: GBrainMaintenanceEntry[];
};
