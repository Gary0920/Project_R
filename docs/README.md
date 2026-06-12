# Project_R 文档入口

本目录保存 Project_R 的正式项目文档。根目录仅保留工程入口、Agent 规则和通用上下文；长期产品、方案、验证、设计和运维资料都应归档到本目录下的分区。

## 目录分工

| 目录 | 职责 | 典型内容 |
|---|---|---|
| `product/` | 产品范围、业务边界、业务工作流和能力盘点 | PRD、业务工作流清单、GBrain 功能盘点 |
| `specs/` | 功能方案、实现规格、流程设计和提示词模板 | GBrain ingest 流程、知识质量方案、功能目标 |
| `milestones/` | 阶段计划、开发流程、迭代进度和历史清理盘点 | 开发流程、V2.0 计划、backlog、适配进度 |
| `validation/` | 测试说明、手工验收、联调记录和验收报告 | Electron 手工清单、Windows 测试、阶段验收 |
| `design/` | UI 设计语言、设计稿、视觉参考和变更说明 | 视觉 token、设计框架、界面调整素材 |
| `operations/` | 安装、运行、维护和 GBrain 运维手册 | Windows setup、worker 策略、runbook |
| `adr/` | 架构决策记录 | 重要技术边界、长期约束、决策历史 |
| `agents/` | Agent 工作流、Skill 设计和协作规则 | Skill 模板、triage 标签、Agent domain |
| `prototypes/` | 原型与设计验证产物 | HTML 原型、设计探索 |

## 核心文档

| 文档 | 用途 |
|---|---|
| [Project_R PRD.md](product/Project_R%20PRD.md) | 产品范围、目标用户和长期能力边界 |
| [Project_R 业务工作流清单.md](product/Project_R%20业务工作流清单.md) | 企业业务 Skill 候选清单与实现状态 |
| [Project_R 开发流程.md](milestones/Project_R%20开发流程.md) | 阶段顺序、任务清单、完成标志和实现状态 |
| [Project_R 开发流程V2.0.md](milestones/Project_R%20开发流程V2.0.md) | 下一阶段产品基座精修主计划 |
| [gbrain-feature-inventory.md](product/gbrain-feature-inventory.md) | GBrain 原生能力盘点矩阵 |
| [gbrain-ingest-workflow.md](specs/gbrain-ingest-workflow.md) | 原始资料进入 GBrain source 的导入、提炼、审核和索引流程 |
| [ui-design-language.md](design/ui-design-language.md) | Project_R 前端视觉语言和 UI 修改约束 |

## 维护规则

- 新需求、产品范围和业务边界放入 `product/`。
- 具体功能如何实现、如何验收放入 `specs/`。
- 阶段计划、任务清单和进度状态放入 `milestones/`。
- 测试清单、验收报告和联调记录放入 `validation/`。
- UI 视觉规范、设计参考和设计变更资料放入 `design/`。
- 安装、运行、维护和故障排查资料放入 `operations/`。
- `Spec/` 是本地 Agent 临时计划缓存，不作为正式项目文档目录。
