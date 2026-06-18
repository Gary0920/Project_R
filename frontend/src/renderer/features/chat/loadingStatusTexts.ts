type LoadingStatusContext = {
  mode: string;
  variant: "reply" | "regenerate";
  hasAttachments: boolean;
  isKnowledgeQuery: boolean;
  activeSkillName: string | null;
  webSearchEnabled: boolean;
  thinkingEnabled: boolean;
};

function uniqueSteps(steps: string[]) {
  return steps.filter((step, index) => steps.indexOf(step) === index);
}

const CHAT_REPLY_TAIL = [
  "正在整理上下文",
  "正在组织回答结构",
  "正在生成回答",
  "正在润色表述",
  "正在做最后检查",
  "即将完成",
];

const CHAT_REGENERATE = [
  "正在重新生成",
  "正在回顾上一轮回答",
  "正在调整表述角度",
  "正在重新组织内容",
  "正在整理上下文",
  "正在生成新版本",
  "正在润色表述",
  "正在做最后检查",
  "即将完成",
];

const AGENT_REPLY = [
  "Agent 执行中",
  "正在理解任务目标",
  "正在拆解执行步骤",
  "正在读取工作区上下文",
  "正在整理执行计划",
  "正在准备步骤状态",
  "正在推进任务",
  "正在汇总结果",
  "正在做最后检查",
  "即将完成",
];

const AGENT_REGENERATE = [
  "正在重新执行",
  "正在回顾上一轮结果",
  "正在调整执行策略",
  "正在整理执行步骤",
  "正在更新任务状态",
  "正在读取上下文",
  "正在重新生成结果",
  "正在汇总输出",
  "即将完成",
];

const QUERY_STEPS = [
  "正在回复",
  "正在识别知识库问题",
  "正在确认查询范围",
  "正在检索相关文档",
  "正在比对多个来源",
  "正在提取关键片段",
  "正在整理引用依据",
  "正在组织回答结构",
  "正在生成回答",
  "正在润色表述",
  "即将完成",
];

const ATTACHMENT_STEPS = [
  "正在回复",
  "正在读取本轮附件",
  "正在解析附件内容",
  "正在提取关键信息",
  "正在关联对话上下文",
  "正在整理上下文",
  "正在组织回答结构",
  "正在生成回答",
  "正在润色表述",
  "即将完成",
];

const WEB_SEARCH_EXTRA = [
  "正在检索联网资料",
  "正在筛选可信来源",
  "正在整合搜索结果",
  "正在核对时效信息",
];

const THINKING_EXTRA = [
  "正在深度推理",
  "正在梳理推理链路",
  "正在校验中间结论",
];

export function buildLoadingStatusTexts(context: LoadingStatusContext): string[] {
  const {
    mode,
    variant,
    hasAttachments,
    isKnowledgeQuery,
    activeSkillName,
    webSearchEnabled,
    thinkingEnabled,
  } = context;

  if (variant === "regenerate") {
    return mode === "agent" ? AGENT_REGENERATE : CHAT_REGENERATE;
  }

  if (mode === "agent") {
    if (activeSkillName) {
      return [
        `已选择 Skill：${activeSkillName}`,
        "正在读取上下文",
        "正在解析任务输入",
        "正在匹配 Skill 流程",
        "正在执行任务",
        "正在整理中间结果",
        "正在生成输出",
        "正在做最后检查",
        "即将完成",
      ];
    }
    return AGENT_REPLY;
  }

  if (isKnowledgeQuery) {
    return QUERY_STEPS;
  }

  if (hasAttachments) {
    const insertAt = 5;
    const head = ATTACHMENT_STEPS.slice(0, insertAt);
    const tail = ATTACHMENT_STEPS.slice(insertAt);
    return uniqueSteps([
      ...head,
      ...(webSearchEnabled ? WEB_SEARCH_EXTRA : []),
      ...(thinkingEnabled ? THINKING_EXTRA : []),
      ...tail,
    ]);
  }

  return uniqueSteps([
    "正在回复",
    "正在理解问题",
    "正在分析提问意图",
    ...(webSearchEnabled ? WEB_SEARCH_EXTRA : []),
    ...(thinkingEnabled ? THINKING_EXTRA : []),
    ...CHAT_REPLY_TAIL,
  ]);
}
