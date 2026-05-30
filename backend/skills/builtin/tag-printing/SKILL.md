---
name: tag-printing
display_name: 标签打印源文件生成
description: 提供项目信息，自动生成标签打印 Excel 源文件（含编号、产品信息、颜色、尺寸等），套用公司 Excel 模板
category: 样品阶段
priority: high
trigger:
  - 帮我生成标签打印文件
  - 打印标签
  - 样品标签打印
  - 制作标签源文件
  - 标签打印 Excel
inputs:
  - name: project_name
    type: string
    label: 项目名称
    required: true
  - name: project_code
    type: string
    label: 项目编号
    required: true
  - name: label_items
    type: text
    label: 标签内容列表（每行一个标签）
    required: true
  - name: template_file
    type: file
    label: 标签打印模板（Excel）
    required: true
    accept: [xlsx, xls]
outputs:
  - type: file
    format: xlsx
    template: 由用户上传的模板文件
references:
  - rules/标签打印规范.md
---

# 标签打印源文件生成

## 目的

在样品阶段，需要为每个样品制作标签（含编号、产品名称、颜色、尺寸、项目信息等），以便打印后贴在样品上。传统做法是手动在 Excel 中逐行填写，耗时且容易出错。本 Skill 自动完成数据填入，用户只需提供标签信息和模板文件。

## 触发条件

- **必要前置条件**：用户已登录，有上传 Excel 模板文件
- **典型触发语**：
  - "帮我生成样品标签打印文件"
  - "打印标签，项目编号 BG2026-001"
  - "制作标签源文件"
  - "标签打印 Excel，项目名称为 XX 项目"
- **非触发场景**：
  - 用户仅询问标签打印的方法而非要求生成文件
  - 用户需打印的不是样品标签（如文档标签、文件夹标签）

## 输入收集步骤

1. 询问项目名称和项目编号（如首条消息未提供）
2. 询问标签内容——提供格式示例：
   ```
   编号 | 产品名称 | 颜色 | 尺寸 | 数量
   T001 | 铝合金框 | 深灰色 RAL7016 | 1200×600mm | 2
   T002 | 玻璃面板 | 透明 | 600×600mm | 1
   ```
3. 要求用户上传标签打印 Excel 模板文件（`.xlsx` 或 `.xls`）
4. 向用户复述确认所有信息

## 处理步骤

1. 从上传的 Excel 模板中读取模板格式（列头、样式、合并单元格等）
2. 解析用户输入的标签内容列表
3. 将标签数据逐行填入模板对应列
4. 填入项目名称和项目编号到模板指定位置（如页眉或第一行）
5. 保存为 `tag-printing_<项目编号>_<时间戳>.xlsx`
6. 让用户预览并确认

## 输出形式

- **主输出**：`tag-printing_<项目编号>_YYYYMMDD-HHMMSS.xlsx`
  - 套用用户上传的模板格式
  - 包含所有标签数据行
  - 项目名称和编号标记在文件中

## 错误处理

| 失败点 | 处理方式 |
|---|---|
| 上传的模板不是 Excel 文件 | 提示用户上传 .xlsx 或 .xls 文件 |
| 模板格式不支持读取 | 返回"模板格式不支持，请使用标准 Excel 模板" |
| 标签内容解析失败 | 显示解析结果，让用户手动修正格式 |
| 文件渲染异常 | 记录日志，向用户返回友好错误 |

## 关联知识

`rules/标签打印规范.md` 应包含：
- 标签内容的格式规范
- 打印设置要求（纸张尺寸、边距等）
- 标签编号规则

## 测试用例

见 `examples/` 目录。

## 维护说明

- 本 Skill 涉及的业务规则（标签编号规则、打印设置）应从知识库读取，不在本文件硬编码
- 修改本 Skill 时同步更新 `references/Project_R 业务工作流清单.md` 中 U03 的状态
