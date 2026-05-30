---
name: skill-template
display_name: <用户可见的 Skill 名称>
description: <一句话描述：什么场景触发，做什么事，输出什么>
category: <对应业务工作流清单的分类，如"项目启动"、"样品阶段"、"通用业务">
priority: high  # high / medium / low
trigger:
  - <触发该 Skill 的自然语言示例 1>
  - <触发示例 2>
  - <触发示例 3>
inputs:
  - name: <字段标识>
    type: string  # string / text / number / date / file / file_list / select / multi_select
    label: <询问用户时显示的中文标签>
    required: true
    # accept: [pdf, docx]   # type=file/file_list 时使用
    # options: [选项1, 选项2]  # type=select/multi_select 时使用
outputs:
  - type: file  # chat_text / file / dingtalk_push / knowledge_review
    format: docx
    template: templates/word/<模板文件名>.docx
references:
  - <相关知识库条目，例 rules/某规则.md>
---

# <Skill 名称>

> 这是 Project_R Skill 的占位模板。复制本模板到 `backend/skills/builtin/<skill-name>/SKILL.md` 后填写；业务状态同步维护在根目录 `Project_R 业务工作流清单.md`。

## 目的

简要说明此 Skill 解决的业务问题。例如：

> 在项目中标后两周内，自动汇总项目核心信息（地区、地址、使用系统、工程量、工期），按公司模板生成《项目材料采购信息总览》并推送给采购部门，避免人工汇总信息遗漏或延迟。

## 触发条件

详细说明意图识别匹配规则。

- **必要前置条件**：例如"用户必须已经登录、必须有该项目的访问权限"
- **典型触发语**：列出 3-5 条用户可能说的话
- **非触发场景**：列出哪些情况下不应触发本 Skill

## 输入收集步骤

按对话顺序列出需要收集的输入项。

1. 询问 / 确认输入项 A（如未在首条消息中提供）
2. 让用户上传所需文件（type=file/file_list 触发上传卡片）
3. 关键信息收集后向用户复述确认，避免误执行

## 处理步骤

逐步说明 Skill 内部的执行流程。

1. 从输入中提取关键字段（用 LLM 或正则）
2. 调用 Wiki Router / RAG 检索 `references` 中列出的知识库条目作为上下文
3. 调用 LLM 生成内容草稿
4. 套用模板渲染成成品文件
5. 让用户预览并确认
6. 执行最终输出（保存文件 / 推送钉钉 / 写入审核队列）

## 输出形式

明确每个 output 的具体形态。

- **主输出**：`<skill-name>_<项目编号>_<时间戳>.docx`，包含哪些字段
- **副输出**（如有）：钉钉推送到哪个群、@哪个角色

## 错误处理

按可能的失败点逐项说明。

| 失败点 | 处理方式 |
|---|---|
| 信息提取不全 | 询问用户手动补充缺失字段 |
| 模板文件缺失 | 返回"未找到模板，请联系管理员" |
| LLM 调用失败 | 走 Claude API 多 Key 降级流程 |
| 文件渲染异常 | 记录日志，向用户返回友好错误 |
| 钉钉推送失败 | 记录日志但不阻断主流程，提示用户手动转发 |

## 关联知识与上下文优先级

`references` frontmatter 字段中列出的条目会被自动检索作为 Skill 上下文。补充说明：

- 为什么需要这些知识：例如"《中标后2周内提交采购信息》定义了交付时限和模板规范"
- 如何使用：作为 LLM 生成时的硬约束 / 软参考
- 全局底层规则：`backend/prompt_presets/global-base-prompt.md` 由后端强制注入，优先级高于 Skill、项目资料、会话附件和用户输入。
- 项目资料：仅在当前工作区/项目对话中可用，不能引用其他项目资料。
- 会话附件：仅作为当前会话临时上下文，不自动进入项目资料库。

## 测试用例

至少准备一组输入输出示例，放在 `examples/` 子目录下：

```
backend/skills/builtin/<skill-name>/
├── SKILL.md
├── prompt.md            # 可选：长 prompt 模板
└── examples/
    ├── input-sample.md  # 模拟用户输入
    └── output-sample.md # 期望输出
```

## 维护说明

- 修改本 Skill 时同步更新根目录 `Project_R 业务工作流清单.md` 中对应行的状态
- 如果 Skill 阶段状态或验收范围变化，同步更新根目录 `Project_R 开发流程.md`
- 如果本 Skill 涉及的业务规则发生变化，先在知识库中更新对应规则文档，再调整本 SKILL.md
- 不要在 SKILL.md 中硬编码业务规则细节，所有规则来自知识库（保持单一信息源）
- 本模板仅描述 Skill 结构，不替代 `docs/agents/skills-design.md` 的设计规范
