/**
 * 空状态快捷入口占位配置。
 * 后续由 Gary 替换为真实 Skill id 或提示词 id；`QuickStartItem.id` 与调用次数统计 key 保持一致即可。
 */
export type QuickStartItem = {
  id: string;
  label: string;
  description?: string;
};

export const QUICK_START_PLACEHOLDERS: QuickStartItem[] = [
  {
    id: "placeholder-email-reply",
    label: "客户英文回复起草",
    description: "根据邮件、顾问意见或质量反馈生成克制回复",
  },
  {
    id: "placeholder-meeting-minutes",
    label: "整理会议纪要",
    description: "从会议文本提取结论、责任人与下一步",
  },
  {
    id: "placeholder-drawing-extract",
    label: "图纸/窗表提取",
    description: "提取尺寸、编号、材料与待核对项",
  },
  {
    id: "placeholder-project-comm",
    label: "项目沟通分析",
    description: "识别风险、争议点与可执行建议",
  },
];
