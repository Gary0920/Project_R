import { useEffect, useMemo, useState } from "react";

import type { ApiClientOptions } from "../../../shared/api/client";
import { getLLMHealth } from "../../../shared/api/health";
import type { LLMProviderStatusResponse } from "../../../shared/api/types";
import { readWebSearchPreference, writeWebSearchPreference } from "../../prompts/sessionPrompt";
import { toModelOption } from "../modelOptions";

export function useAppModelControls(apiOptions: ApiClientOptions) {
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(readWebSearchPreference);
  const [temperature, setTemperature] = useState<number | undefined>(undefined);
  const [llmProviders, setLlmProviders] = useState<LLMProviderStatusResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelConfigError, setModelConfigError] = useState("");
  const [selectedModelKey, setSelectedModelKey] = useState<string | null>(null);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);

  const modelOptions = useMemo(() => {
    return llmProviders
      .filter((provider) => provider.configured)
      .map(toModelOption)
      .sort((a, b) => Number(b.isDefault) - Number(a.isDefault) || a.label.localeCompare(b.label, "zh-CN"));
  }, [llmProviders]);
  const selectedModelOption = modelOptions.find((option) => option.key === selectedModelKey) ?? modelOptions.find((option) => option.isDefault) ?? modelOptions[0] ?? null;

  useEffect(() => {
    let mounted = true;
    setModelsLoading(true);
    setModelConfigError("");
    getLLMHealth(apiOptions)
      .then((health) => {
        if (!mounted) return;
        setLlmProviders(health.providers);
      })
      .catch(() => {
        if (!mounted) return;
        setLlmProviders([]);
        setModelConfigError("无法读取模型配置");
      })
      .finally(() => {
        if (mounted) setModelsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions]);

  useEffect(() => {
    if (modelOptions.length === 0) {
      setSelectedModelKey(null);
      return;
    }
    if (selectedModelKey && modelOptions.some((option) => option.key === selectedModelKey)) return;
    setSelectedModelKey((modelOptions.find((option) => option.isDefault) ?? modelOptions[0]).key);
  }, [modelOptions, selectedModelKey]);

  function toggleWebSearch() {
    setWebSearchEnabled((current) => {
      const next = !current;
      writeWebSearchPreference(next);
      return next;
    });
  }

  return {
    modelConfigError,
    modelMenuOpen,
    modelOptions,
    modelsLoading,
    selectedModelKey,
    selectedModelOption,
    setModelMenuOpen,
    setSelectedModelKey,
    setTemperature,
    setThinkingEnabled,
    temperature,
    thinkingEnabled,
    toggleWebSearch,
    webSearchEnabled,
  };
}
