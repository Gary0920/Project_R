import type { LLMProviderStatusResponse } from "../../shared/api/types";

export type ModelOption = {
  key: string;
  label: string;
  provider: string;
  profile: string;
  description: string;
  model: string;
  supportsVision: boolean;
  isDefault: boolean;
};

const MODEL_COPY: Record<string, { label: string; description: string }> = {
  deepseek: { label: "DeepSeek", description: "文本对话、推理输出" },
  claude: { label: "Claude", description: "复杂推理与长文处理" },
  openai: { label: "OpenAI", description: "通用兼容接口" },
  mimo: { label: "MiMo", description: "多模态理解" },
};

const MODEL_CAPABILITY_COPY: Record<string, string> = {
  "deepseek-flash": "文本对话、快速推理",
  "deepseek-pro": "文本对话、复杂推理",
  "mimo-v2-5": "文本/图像/视频/音频理解",
  "mimo-v2-5-pro": "文本/图像理解，复杂推理",
};

export function toModelOption(status: LLMProviderStatusResponse): ModelOption {
  const profile = status.profile ?? status.provider;
  const copy = MODEL_COPY[status.provider] ?? {
    label: status.provider.toUpperCase(),
    description: "已配置模型接口",
  };
  const normalizedModel = status.model.toLowerCase().replace(/\./g, "-");
  const capabilityDescription = MODEL_CAPABILITY_COPY[profile] ?? MODEL_CAPABILITY_COPY[normalizedModel];
  const supportsVision = status.supports_vision ?? Boolean(capabilityDescription?.includes("图像"));
  return {
    key: profile,
    profile,
    provider: status.provider,
    label: status.label || copy.label,
    description: capabilityDescription || status.description || copy.description,
    model: status.model,
    supportsVision,
    isDefault: status.default,
  };
}
