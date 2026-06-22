# 标准规范 PDF 提炼 Skill

## 功能

将标准规范 PDF 转换为结构化 Markdown 知识手册，覆盖条款要求、参数表格、适用范围、项目控制点。

## 适用范围

- 建筑门窗标准（AS 2047、AS 4200、AS 1288 等）
- 其他行业标准（机械、食品、IT 等）
- 不限于特定标准类型，模板通用

## 提炼原则

### 内容深度

- **逐条列出原文具体规定**，禁止压缩成一句概括
- 五金要求不只是"应适合用途"，而要列出：部件清单、操作力要求、锋利边缘禁止、防腐要求、室内可调整性等
- Security 条款必须引用标准原文的具体措辞，不能概括为"合理安全水平"
- 公差要求必须提取原文的具体数值（成品公差和材料公差分开）
- 防水/安装节点必须提取现场可执行的参数（间距、嵌入深度、翻边高度等）

### 参数表格

- **参数数据必须用 Markdown 表格格式**：涉及多行多列的参数数据（如等级表、压力表、公差表等），必须用 `| 列1 | 列2 |` 表格格式输出，不得用纯文本列表或段落罗列
- **关键表格必须完整保留**：不得用"见原表"替代表格内容，必须把表格的行列数值写入输出

### 语言规则

- 正文写中文，不要每句话后面都跟一遍 English 翻译
- 只有标准编号（AS/NZS 4420.1）、技术参数（U-value、SHGC）、条款号（Clause 2.3.2.6）这些本身是英文术语的才保留英文
- 表格列标题可以用"中文 / English"对照，方便两种语言的人看
- 不需要"中文：xxx。English：xxx。"这种成对重复

### 格式要求

- 正文只写标准原文的具体条款要求
- 个别需额外提醒的地方用 `> **项目建议：**` 引用块标注
- 所有不确定的内容收在末尾"待审核问题"中

## 输出结构

```markdown
# {标准名称}

## 审核状态 / Review Status
（原始页数、已分析页数、视觉辅助、主要不确定性）

## 标准适用范围 / Standard Scope
### 适用产品与场景 / Applicable Products and Scenarios
### 不适用范围 / Exclusions

## 核心引用标准 / Core Referenced Standards
| 标准编号 / Standard | 名称 / Name | 用途 / Purpose | 涉及条款 / Clauses |

## 核心性能要求 / Core Performance Requirements

## [按主题组织的性能章节]
### 主题名
- **测试标准 / Test Standard**
- **标准原文要求 / Standard Requirements**（逐条列出，禁止压缩）
- **参数表 / Parameter Table**（Markdown 表格格式，完整保留行列数值）
- **证据 / Evidence**
- > **项目建议：**（如有）

## 材料与表面处理 / Materials and Finishes（如适用）

## 五金与紧固件 / Hardware and Fasteners（如适用）
（逐条列出原文具体规定）

## 安全要求 / Security Requirements（如适用）
（引用标准原文具体措辞）

## 公差要求 / Tolerances（如适用）
（成品公差和材料公差分开，具体数值必须写入）

## 防水与安装节点 / Weatherproofing and Flashing（如适用）
（现场可执行的安装参数：间距、嵌入深度、翻边高度等）

## 制造与装配 / Construction and Tolerances（如适用）

## 安装要求 / Installation Requirements（如适用）

## 标签与证书 / Labelling and Certificate（如适用）

## 附录要点 / Appendix Highlights（如有）

## 参数与表格汇总 / Parameters and Tables Summary

## 项目执行控制清单 / Project Execution Control Checklist
| 阶段 / Phase | 检查项 / Check Item | 判定规则 / Decision Rule | 风险等级 / Risk Level | 相关条款 / Clause | 页码 / Page |

### 关键参数展开 / Key Parameters Detail
（需要展开解释的核心参数：定义、衡量、作用、涉及条款）

## 待审核问题 / Review Questions
（不确定、OCR风险、表格错位、公式不完整等）
```

## 大文件处理

- 超过 40 页的标准 PDF 自动拆分为两半分别提取，再合并结果
- 拆分后每半部分独立生成完整结构，合并时保留两部分的所有章节

## 注意事项

- 本 Skill 使用 MiMo V2.5 模型进行视觉辅助提取
- 输出标记为 `pending_review`，需人工审核后才能入库
- 不要编造 PDF 中没有的内容
- 无法确认的信息放入"待审核问题"
