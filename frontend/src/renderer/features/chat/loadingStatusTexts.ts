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

function shuffledSteps(steps: string[]) {
  const result = [...steps];
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [result[index], result[swapIndex]] = [result[swapIndex], result[index]];
  }
  return result;
}

// 统一加载文案库：直接删除不喜欢的句子，保留顺眼的句子即可。
// 这些文案只用于等待时的氛围轮换，不代表真实内部执行状态。
const LOADING_STATUS_TEXTS = [
  "正在回复",
  "正在理解问题",
  "正在把话说顺",
  "正在生成回答",
  "正在做最后检查",
  "正在让句子站直",
  "正在换一套说法",
  "正在拆掉重装",
  "正在把上一版返工",
  "正在补一遍密封胶",
  "正在推进任务",
  "正在汇总结果",
  "正在执行任务",
  "正在生成输出",
  "正在确认查询范围",
  "正在比对多个来源",
  "正在整理引用依据",
  "正在让资料对齐孔位",
  "正在给引用打结构胶",
  "正在从图纸堆里抬头",
  "正在拆除过期胶条",
  "正在脑内放样",
  "正在校准副框",
  "正在找那颗不见的自攻钉",
  "正在给答案打耐候胶",
  "正在复核洞口尺寸",
  "正在擦亮 Low-E 玻璃",
  "正在等结构胶表干",
  "正在把节点图翻到正面",
  "正在确认开启扇方向",
  "正在给回答装限位器",
  "正在检查排水孔有没有堵",
  "正在把铝型材码齐",
  "正在让幕墙顾问点头",
  "正在拧紧最后一颗螺丝",
  "正在看玻璃有没有自爆风险",
  "正在把节点收口收漂亮",
  "正在给答案贴保护膜",
  "正在检查五金件心情",
  "正在让窗扇别再漏风",
  "正在把胶条塞回正确槽口",
  "正在帮甲方冷静一下",
  "正在让施工队先别急",
  "正在撕保护膜",
];

export function buildLoadingStatusTexts(context: LoadingStatusContext): string[] {
  const selectedSkillPrefix = context.activeSkillName ? [`已选择 Skill：${context.activeSkillName}`] : [];
  return uniqueSteps([
    ...selectedSkillPrefix,
    ...shuffledSteps(LOADING_STATUS_TEXTS),
  ]);
}
