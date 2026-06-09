# 8.D 项目质量与文件预览 — 技术设计文档

Version: v1.0  
Date: 2026-06-09  
Status: Draft for implementation  
Supersedes: `docs/8d-project-knowledge-quality-prd.md` (产品层 PRD)  
Scope: 模块架构、数据流、接口合约、实现顺序

---

## 1. 当前状态

### 已完成基线 (D0)

| 项 | 状态 |
|---|---|
| TEST 样本目录 `backend/workspace_data/project/TEST/TEST/` | 24 个文件 / 7 个子目录 |
| 14 条质量回归 fixture | `backend/tests/fixtures/gbrain_project_quality_regression_cases.json` |
| Fixture 只读预检脚本 | `backend/scripts/gbrain_project_quality_regression.py --workspace-preflight` |
| query question.md 排除 | manifest 不包含、gbrain-ready 不包含 |
| 首轮 TEST ingest | compiled=24, pending_extractor_capability=1(spreadsheet), failed=0 |
| Extractor classifier | `core/extractor_classifier.py` — 按后缀 + PDF 启发式分类 |
| 模型策略 | `core/preprocess_model_policy.py` — DeepSeek/MiMo V2.5 路由 |
| PDF 结构化提取 | `core/pdf_structured_extraction.py` — MiMo V2.5，单 prompt |
| 图片结构化提取 | `core/image_structured_extraction.py` — MiMo V2.5，通用 prompt |
| EML 提取 | `core/email_structured_extraction.py` — 含附件递归 |
| 会议转写/提炼 | `core/media_transcription.py` + `core/meeting_structured_extraction.py` |
| DOCX 提取 | `core/docx_text_preprocess.py` |
| 项目 ingest 主流程 | `core/gbrain_project_ingest.py` — compile + manifest + gbrain-ready |
| GBrain source status | `GBrainAdapter.project_source_status()` — 含 path_matches 校验 |

### D0 遗留问题

- `project_source_status` 返回 `page_count=26`（真实 Markdown 是 24 → GBrain 中为 24 live pages）、`clone_state=corrupted`（GBrain CLI 返回历史状态，不影响功能，但 UI 显示异常）。
- 需在 backend 侧对 GBrain 返回做二次修复：page_count 以 `gbrain-ready/` 实际 Markdown 数为准、clone_state 不可用时显示为 `"available"`。

### 未完成 (D1–D8)

```
D1 回归查询   ─── 扩展回归脚本：--query / --think 模式 + 评分 + 报告
D2 意图+排序   ─── query intent classifier + GBrain 检索排序调整
D3 表格        ─── spreadsheet-preprocess（openpyxl 提取）
D4 图纸排期    ─── 分类 prompt + 结构化校验 + page-level citation
D5 图片字段    ─── 支付截图 / 内部联系单 schema
D6 会议质量    ─── 重复检测 + 质量评分 + 降权
D7 引用+预览   ─── 统一引用合约 + 后端预览 API + 前端预览面板
D8 管理报告    ─── 质量报告存储 + 管理后台展示
```

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend                            │
│  [Chat] → [Preview Panel] → [Admin Quality Report UI]   │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼────────────────────────────────┐
│                   Backend API Layer                       │
│  /api/projects/{id}/query          (GBrain query)        │
│  /api/projects/{id}/preview/{file}  (source preview)     │
│  /api/admin/quality/reports        (quality reports)     │
│  /api/projects/{id}/quality/report (project report)      │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                8.D Quality Core Layer                     │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Query Intent │  │  Ranking     │  │ Citation     │  │
│  │ Classifier   │──│  Adjuster    │──│ Normalizer   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Regression   │  │ Quality      │  │ Source Meta  │  │
│  │ Runner       │  │ Report Gen   │  │ Normalizer   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│           Preprocessor & Ingest Layer                     │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Existing:  PDF · Image · EML · Meeting · DOCX    │  │
│  │  New:       Spreadsheet                            │  │
│  └────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                    GBrain Adapter                         │
│  source import → chunk → embed → query/think → citation  │
└─────────────────────────────────────────────────────────┘
```

### 模块职责

| 模块 | 文件定位 | 职责 |
|---|---|---|
| Query Intent Classifier | `core/project_query_intent.py` | 分析用户问题 → 推断 `file_kind_hint` |
| Ranking Adjuster | `core/project_query_ranking.py` | 调整 GBrain 排序结果：同类加权、会议降权 |
| Citation Normalizer | `core/project_citation.py` | 统一引用格式：page/region/sheet-row/timestamp/text_span |
| Source Meta Normalizer | `core/project_source_metadata.py` | 跨文件类型稳定证据词汇表 |
| Regression Runner | `core/project_quality_regression.py` | 加载 fixture → query/think → 评分 → 报告 |
| Quality Report Gen | `core/project_quality_report.py` | 回归报告 JSON → 可展示 + 可归档 |
| Spreadsheet Preprocessor | `core/spreadsheet_preprocess.py` | XLSX → 结构化 Markdown |
| Field Extraction Schema | `core/image_field_schemas.py` | 支付截图 / 联系单字段 schema |
| Meeting Quality | `core/meeting_quality.py` | 重复检测、质量评分 |
| File Preview API | `routers/project_preview.py` | 文件预览端点 |

---

## 3. 模块详细设计

### 3.1 D1 — Regression Runner (`core/project_quality_regression.py`)

**输入**: 14 条 fixture（`gbrain_project_quality_regression_cases.json`）+ 可选 `--query` / `--think` 模式  
**输出**: JSON 报告保存到 `_preprocessed/project/TEST/TEST/manifests/quality-reports/{run_id}.json`

#### 评分分类

| 分类 | 含义 | 是否应通过 |
|---|---|---|
| `pass` | 回答命中期望来源且含必要 terms | 是 |
| `wrong_source` | 回答来自错误来源类型（如非会议问题命中会议） | 否 |
| `missing_answer_point` | 来源正确但缺少关键答案点 | 否 |
| `missing_citation` | 答案正确但缺少引用位置 | 否 |
| `known_gap` | fixture 标记为 known_gap，不计入失败 | 跟踪 |
| `unexpected_pass` | known_gap 问题意外通过 | 跟踪 |
| `service_unavailable` | GBrain 服务不可用 | 跳过 |
| `meeting_false_positive` | 非会议问题第一命中为会议 source | 子标记 |

#### 数据流

```
load_fixture()
  ↓
──query mode──→ query_project_source() → 评分 → 报告条目
──think mode──→ think_project_source() → 评分 → 报告条目
  ↓
merge_report() → _write_report() → quality-reports/{run_id}.json
```

#### CLA

```python
@dataclass
class RegressionCase:
    id: str
    file_kind: str
    expected_status: str  # "should_pass" | "known_gap"
    query: str
    source_file: str
    expected_location: dict
    expected_answer: dict

@dataclass
class RegressionResult:
    case_id: str
    status: str  # pass | wrong_source | missing_answer_point | ...
    first_hit_source: str | None
    first_hit_file_kind: str | None
    answer_text: str | None
    citation: dict | None
    missing_terms: list[str]
    meeting_false_positive: bool
    answer_points: list[str]

@dataclass
class QualityReport:
    run_id: str
    generated_at: str
    source_id: str
    mode: str  # "query" | "think"
    results: list[RegressionResult]
    summary: dict  # pass_count, fail_count, known_gap_count, ...
```

#### 单元测试策略

- Mock `GBrainAdapter.query_project_source()` 返回固定回答
- 验证 wrong_source 分类：非会议问题返回会议 source
- 验证 known_gap 不计入 failure
- 验证 report JSON 结构

---

### 3.2 D2 — Query Intent Classifier (`core/project_query_intent.py`)

#### 设计原则

- **轻量规则优先**：不需要 LLM 调用，模式匹配即可覆盖 90% 用例
- **可扩展**：`file_kind` → 关键词规则表，后续可升级为 ML/LLM 分类
- **输出**：`QueryIntent` dataclass，含 `file_kind_hint`, `confidence`, `source_category_hint`

#### 规则表

| 用户问题含 | file_kind_hint | confidence |
|---|---|---|
| "图纸"、"平面图"、"窗号"、"立面"、"floor plan"、"drawing" | `pdf_drawing` | `high` |
| "排期"、"工期"、"计划完成"、"Duration"、"Start / Finish" | `pdf_schedule` | `high` |
| "支付"、"金额"、"花费"、"付款"、"pay"、"screenshot" | `image_payment` | `high` |
| "内部联系单"、"补货"、"BG0806"、"签证"、"联系单" | `image_contact_sheet` | `high` |
| "会议"、"Gary 提出"、"讨论"、"decided"、"meeting" | `meeting_*` | `high` |
| "邮件"、"Daisy"、"推荐"、"Skylight"、"email" | `email` | `high` |
| "材料清单"、"GL01"、"玻璃规格"、"ML"、"BOM"、"材料" | `spreadsheet` | `high` |
| "注意事项"、"适配颜色"、"五金"、"Rooster"、"notes" | `office_doc` | `medium` |
| "合同"、"报价"、"quotation"、"contract" | `office_contract` | `medium` |

#### CLA

```python
@dataclass
class ProjectQueryIntent:
    file_kind_hint: str | None          # "pdf_drawing" | "pdf_schedule" | ...
    source_category_hint: str | None    # "technical" | "meetings" | ...
    confidence: str                     # "high" | "medium" | "low"
    matched_patterns: list[str]
    raw_query: str

def classify_project_query(query: str) -> ProjectQueryIntent: ...
```

#### TEST 样本覆盖验证

| Fixture ID | Query | 期望 file_kind_hint |
|---|---|---|
| test_floor_plan_l17_window_count_pdf | "L17 层图纸里有多少个窗？" | `pdf_drawing` |
| test_window_schedule_w19_size_pdf | "L3-15 W19这个窗的宽高尺寸是多少？" | `pdf_drawing` |
| test_programme_shop_drawing_duration_pdf | "项目排期中L6-L39 Shop Drawing...天数？" | `pdf_schedule` |
| test_payment_screenshot_amount_image | "支付截图中，花费了多少钱？" | `image_payment` |
| test_internal_contact_replenishment_reason_image | "内部联系单 BG0806-LXD01...为什么补货？" | `image_contact_sheet` |
| test_meeting_new_knowledge_system_transcript_docx | "会议中Gary提出了...知识库系统？" | `meeting_*` |
| test_email_skylight_glass_recommendation_eml | "邮件中 daisy推荐...什么玻璃？" | `email` |
| test_material_list_gl01_glass_spec_spreadsheet | "材料清单中，GL01的玻璃规格？" | `spreadsheet` |
| test_hardware_color_adaptation_notice_docx | "注意事项文件中，适配颜色五金件？" | `office_doc` |

---

### 3.3 D2 — Ranking Adjuster (`core/project_query_ranking.py`)

#### 设计

在项目 `/query` 流程中插入排序调整层，位于 GBrain `think` 返回之后、最终答案组装之前。

**当前流程**:
```
用户 query → GBrainAdapter.query_project_source() → raw results → answer
```

**新流程**:
```
用户 query → IntentClassifier → GBrainAdapter.query_project_source() 
           → RankingAdjuster.adjust(results, intent) → answer
```

#### 调整策略

| 场景 | 规则 |
|---|---|
| intent.file_kind_hint 非空 | 同类 file_kind source 权重 +50%（boost_factor=1.5） |
| intent.file_kind_hint = meeting 以外的类型 | 会议转写 chunk 权重 -40%（penalty_factor=0.6） |
| query 含数字/窗号/材料编号 | 精确 metadata 匹配 +80%（boost_factor=1.8） |
| 置信度为 high | 强排序：同类在前，异类在后 |
| 置信度为 medium/low | 软排序：同类适当提前 |

#### CLA

```python
@dataclass
class RankedSource:
    source_path: str
    source_file_kind: str | None
    original_score: float
    adjusted_score: float
    boost_reason: str | None

def adjust_project_ranking(
    results: list[dict],
    intent: ProjectQueryIntent,
    source_metadata: list[SourceMetadata],
) -> list[RankedSource]: ...
```

#### 单元测试

- 支付截图 query + 会议转写 chunk + 支付截图 chunk → 支付截图排第一
- 图纸 query + 会议 chunk + 图纸 chunk → 图纸排第一
- 材料清单 query + XLSX chunk + 会议 chunk → XLSX 排第一
- 无匹配类别的 query → 原始排序不变

---

### 3.4 D3 — Spreadsheet Preprocessor (`core/spreadsheet_preprocess.py`)

#### 设计

**输入**: `.xlsx` / `.xlsm` / `.xls` 文件  
**输出**: GBrain-ready Markdown + manifest `compiled`  
**工具**: `openpyxl`（现有依赖，已在 `pyproject.toml` 中）

#### 提取策略

1. Open workbook, 枚举所有 visible sheets
2. 每 sheet:
   - 检测表头行（首行非空）
   - 提取所有非空行
   - 识别材料编号列（通过列名启发式：`"编号"`、`"Code"`、`"ITEM"`、`"Name"`、`"TYPE"` 等）
   - 为含编号的行输出 Markdown 表格行
3. 合并单元格处理：取左上角值，右侧/下方合并视为重复
4. 行数上限：默认最大 200 行/sheet，超出则截断 + 说明
5. 输出格式：

```markdown
---
source_scope: project
source_file: 05-生产与发货/260506 ML (材料清单) Rev 01.xlsx
preprocess_skill: spreadsheet-preprocess
preprocess_version: 1.0.0
file_kind: spreadsheet
sheet_count: 3
---

# 材料清单 Rev 01

## Sheet: Glass （玻璃）

| Name(编号) | TYPE(名称) | 规格 | ... |
|---|---|---|---|
| GL01 | ... | ... | ... |

### Source Evidence
- Sheet: Glass（玻璃）, Row 3-42
- Material codes detected: GL01, GL02, ...

## Preprocess Notes
- 第 3 行包含合并单元格，取左上角值
- 行数上限 200，本 sheet 未超限
```

#### 测试

- `tests/test_spreadsheet_preprocess.py`:
  - 用临时 XLSX fixture 验证 sheet/table/row 提取
  - `GL01` 行能进入 Markdown
  - 空表不崩溃
  - 合并单元格正确处理
  - 隐藏 sheet 跳过
  - 公式值读取（data_only=True）
  - 损坏文件 → `failed_retryable`
  - manifest 状态 `compiled`

---

### 3.5 D4 — 图纸/排期 PDF 结构化提炼改进

#### 当前状态

`core/pdf_structured_extraction.py` 用单一 prompt 处理所有 PDF，无图纸/排期分类。

#### 改进设计

##### 图纸/版式分类

在 `_classify_pdf()` 基础上增加图纸子分类：

| 特征 | 子分类 | prompt 模板 |
|---|---|---|
| 文件名含 "floor plan"/"平面图"/"drawing" | `drawing_general_arrangement` | `prompts/pdf-drawing-ga-v2.txt` |
| 文件名含 "WS"/"窗表"/"window schedule" | `drawing_window_schedule` | `prompts/pdf-drawing-ws-v1.txt` |
| 文件名含 "programme"/"排期"/"supply programme" | `drawing_schedule` | `prompts/pdf-drawing-schedule-v1.txt` |
| 文件名含 "shop drawing" | `drawing_shop_drawing` | `prompts/pdf-drawing-sd-v1.txt` |
| 默认 | `general_pdf` | 现有 prompt |

##### 每个子分类 prompt 提取重点

**窗表 (WS)**:
```
提取窗表全部行：窗号(W19等)、宽(Width)、高(Height)、数量、楼层范围
输出 Markdown 表格
对每行标注页码
缺宽高数据 → "未提取" 标记，不编造
```

**排期表**:
```
提取任务行：Task Name / Duration / Start / Finish / Predecessors
对每行标注页码
工期格式化为"X 天"
计划完成日期格式化为"YYYY-MM-DD"
```

**图纸 (GA/Shop Drawing)**:
```
识别图纸类型、楼层、图号、窗号/索引
提取尺寸表、材料/玻璃表
页码标注
缺失字段 → needs_review
```

##### 结构化校验后处理

```python
def validate_drawing_extraction(
    markdown: str,
    pdf_path: Path,
    subkind: str,
) -> dict[str, Any]:
    """校验提取质量。返回缺失字段、可疑值、建议状态。"""
```

校验规则：
- 窗表必须包含 `W\d+` 模式的窗号
- 排期必须包含 Duration 或 Finish 字段
- 图纸必须包含页码
- 无索引字段时 → `review_status = "needs_review"`、manifest 标志

#### 测试

- 用固定 prompt 响应 fixture 测试后处理
- `240704 Orama [Floor Plans].pdf` → page 9 应含 `LEVEL 17`
- `240715 Orama [WS].pdf` → 应含 `W19` + 宽高
- `260205 Madeline [Facade Supply Programme] Rev04.pdf` → 应含 `L6-L39 Shop Drawing`

---

### 3.6 D5 — 图片/截图字段化提炼

#### 当前状态

`core/image_structured_extraction.py` 通用 prompt，输出自然语言描述。

#### 改进设计

##### 分类字段 schema

增加 `core/image_field_schemas.py`：

```python
@dataclass
class PaymentScreenshotFields:
    amount: str | None        # "68.00"
    currency: str | None      # "CNY" | "USD"
    direction: str | None     # "outgoing" | "incoming"
    payment_time: str | None  # ISO-8601
    payment_method: str | None  # "wechat" | "alipay" | "bank_transfer"
    counterparty: str | None  # 交易对方
    region: str | None        # 金额区域描述

@dataclass
class ContactSheetFields:
    document_number: str | None      # "BG0806-LXD01"
    replenishment_reason: str | None # 补货原因
    replenishment_items: list[str]   # 补货内容清单
    approval_notes: str | None       # 审批备注
    region: str | None               # 关键区域描述
```

##### 提取流程

```
image_structured_extraction.py
  → _detect_image_subkind()           # 文件名 + prompt 响应 → "payment" / "contact_sheet"
  → _extract_structured_fields()      # 二次 prompt 或后处理正则
  → markdown 中增加 `## Extracted Fields` 块
  → 原 narrative 保留为 `## Description`
```

##### 输出格式

```markdown
# 支付截图服务器.png

## Description
（原自然语言描述保留）

## Extracted Fields
- **金额 / Amount**: 68.00 CNY
- **方向 / Direction**: 支出 (outgoing)
- **支付时间**: 2026-01-15 14:23
- **支付方式**: 微信支付
- **交易对方 / Counterparty**: XX 有限公司

## Source Evidence
- **Source**: 支付截图服务器.png
- **Region**: 金额区域（右下角账单详情区域）

## Preprocess Notes
- OCR 置信度: 高
- 字段提取状态: complete
```

#### 测试

- 固定 MiMo 响应 → 字段解析
- 金额 `-68.00` → `amount=68.00, direction=outgoing`
- 缺字段 → 不编造
- 字段化 Markdown 可被 query regression 命中

---

### 3.7 D6 — 会议转写质量控制

#### 设计

##### 重复文本检测

```python
def detect_repeated_text(
    transcript_text: str,
    min_repeat_length: int = 20,
    threshold_ratio: float = 0.3,
) -> dict[str, Any]:
    """
    检测 ASR 转写中的重复短语。
    返回: {repeated: bool, segments: [...], repeated_chars: int, ratio: float}
    """
```

##### 质量分类

| 等级 | 条件 | 操作 |
|---|---|---|
| `good` | 无重复、连贯、有分段 | 正常索引、正常权重 |
| `fair` | 少量重复，内容仍可理解 | 正常索引，标记 manifest |
| `poor` | 大量重复 (>30%) | 索引，降权 50%，manifest 标记 `asr_quality: poor` |
| `unusable` | 几乎全部重复或噪声 | 索引但降权 80%，manifest 标记 |

##### Manifest 质量字段

在会议源项目的 manifest metadata 中新增：

```yaml
meeting_quality:
  asr_quality: good | fair | poor | unusable
  repeated_ratio: 0.0
  has_repeated_text: false
  quality_checks:
    - check: repeated_text_detection
      passed: true
```

##### 检索降权集成

在 Ranking Adjuster 中：  
`intent != meeting 且 source.meeting_quality.asr_quality in (poor, unusable)` → `penalty_factor=0.4`

#### 测试

- 重复文本 fixture → detected
- 正常转写 → not detected
- 降权逻辑集成测试

---

### 3.8 D7 — 引用定位与文件预览

#### 设计

##### 统一引用合约

跨文件类型的引用格式，前端和后端共用：

```python
@dataclass
class SourceReference:
    source_file: str               # 原始文件路径（相对 workspace root）
    source_url: str                # /api/projects/{id}/preview/{encoded_path}
    file_kind: str
    reference_type: str            # "page" | "region" | "sheet_row" | "timestamp" | "text_span"
    page: int | None               # PDF page number
    region: str | None             # image region description
    sheet: str | None              # spreadsheet sheet name
    row: int | None                # spreadsheet row number
    timestamp: str | None          # meeting timestamp "HH:MM:SS"
    text_span: str | None          # DOCX/MD text snippet
    citation_text: str | None      # 引用的原文摘要
```

##### 后端预览 API

```
GET /api/projects/{workspace_id}/preview/{encoded_path}
Authorization: Bearer <token>
```

响应：

```json
{
  "file": "02-图纸与技术资料/240704 Orama [Floor Plans].pdf",
  "file_kind": "pdf_drawing",
  "size": 245678,
  "mime_type": "application/pdf",
  "preview": {
    "type": "pdf",
    "url": "/api/projects/{workspace_id}/raw/{encoded_path}",
    "page_count": 12
  },
  "gbrain_ready_markdown": "/api/projects/{workspace_id}/gbrain-ready-preview/{encoded_path}"
}
```

预览类型：

| 文件类型 | preview.type | preview 内容 |
|---|---|---|
| PDF | `pdf` | 直接提供 raw file + page_count |
| Image | `image` | raw file + 区域叠加提示 |
| DOCX | `text` | HTML rendered from python-docx + Markdown 版本 |
| XLSX | `sheet_table` | HTML 表格预览 + sheet list |
| EML | `email` | 发件人/主题/正文/附件列表 |
| MP4/音频 | `media` | 文件下载 + 转写 Markdown 链接 |
| Markdown | `markdown` | 渲染的 Markdown + raw |

##### 前端预览面板

**位置**: 右侧常驻工具面板，GBrain 引用来源点击后打开

**组件**:
```
SourcePreviewPanel
├── Header: 文件名 + 文件类型图标 + 关闭
├── Tab: 原始文件 / 提炼内容
│   ├── 原始文件: iframe/embed (PDF) | <img> (图片) | 渲染文本 (文本类)
│   └── 提炼内容: 对应 gbrain-ready Markdown 渲染
└── Footer: 卷回原文链接 + 文件详情
```

**交互**:
- GBrain 回答中的引用 `[来源: 240704 Orama [Floor Plans].pdf (p.9)]` 点击打开预览面板
- 预览面板高亮对应区域（PDF page / 图片区域 / sheet 行）
- 预览面板支持定位到引用位置

#### 测试

- Permission: 项目成员可预览，外部用户 403
- PDF: 返回 raw + page_count
- Image: 返回 raw + region metadata
- DOCX: 返回 HTML + Markdown 链接
- 无权限: 404

---

### 3.9 D8 — 管理后台质量报告

#### 设计

##### 报告存储

每次 D1 回归运行结果保存至：

```
backend/workspace_data/_preprocessed/
  project/TEST/TEST/manifests/quality-reports/
    {run_id}.json
```

同步一份到 admin 可见的聚合目录：

```
backend/workspace_data/_preprocessed/_quality-reports/
  project-TEST/
    {run_id}.json
```

##### 报告内容

```json
{
  "run_id": "2026-06-09T10-30-00",
  "mode": "query",
  "source_id": "project-test-6-test",
  "generated_at": "2026-06-09T10:30:00Z",
  "summary": {
    "total": 14,
    "pass": 3,
    "fail": 3,
    "known_gap": 8,
    "unexpected_pass": 0,
    "wrong_source": 1,
    "meeting_false_positive": 1,
    "service_unavailable": 0
  },
  "pass_rate (should_pass)": "3/3 = 100%",
  "results": [
    {
      "case_id": "...",
      "status": "pass",
      "first_hit_source": "...",
      "first_hit_file_kind": "pdf_drawing"
    }
  ],
  "known_gaps": [
    "test_floor_plan_l17_window_count_pdf",
    "test_material_list_gl01_glass_spec_spreadsheet"
  ]
}
```

##### 管理后台 API

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/admin/quality/reports` | GET | 列出所有报告（分页） |
| `/api/admin/quality/reports/{run_id}` | GET | 获取单份报告 |
| `/api/admin/quality/reports/{run_id}/json` | GET | JSON 下载 |
| `/api/projects/{workspace_id}/quality/report/latest` | GET | 项目最新报告 |

##### 管理后台 UI

在现有管理后台的 GBrain 状态下新增 "质量报告" 子区域：

```
质量报告
┌──────────────────────────────────────────┐
│ 项目          │ 日期       │ 通过率     │
├──────────────────────────────────────────┤
│ TEST          │ 2026-06-09  │ 100%      │
│ ...           │ ...         │ ...       │
└──────────────────────────────────────────┘

点击 → 展开详情：每题的 pass/fail/known_gap 标签
       → 首次命中来源
       → 回答要点匹配情况
```

#### 测试

- 报告生成单元测试（mock 回归结果）
- API 权限测试（admin / 非 admin）
- 前端 report totals 展示验证

---

## 4. 实现顺序

基于产品 PRD 的优先级和工程依赖关系：

```
Phase 1 — 回归引擎（D1 + D8 底座）
  ├── D1: 扩展回归脚本 — query/think 模式
  ├── D1: 评分分类实现（pass/fail/wrong_source/meeting_false_positive）
  ├── D8: 报告 JSON 存储
  └── D0: 修复 project_source_status page_count/clone_state

Phase 2 — 意图 + 排序（D2）
  ├── D2: Query Intent Classifier（规则版本）
  ├── D2: Ranking Adjuster（同类加权 + 会议降权）
  └── 端到端回归验证：支付截图排第一

Phase 3 — 图片字段 + 表格（D3 + D5）
  ├── D5: PaymentScreenshotFields schema
  ├── D5: ContactSheetFields schema
  ├── D3: spreadsheet-preprocess 基本提取
  └── 回归验证：GL01 答案、支付截图金额

Phase 4 — 图纸排期改进（D4）
  ├── D4: PDF 子分类 prompt（WS / Schedule / GA）
  ├── D4: 结构化校验后处理
  └── 回归验证：L17 窗、W19 尺寸、排期 Duration

Phase 5 — 会议质量 + 引用预览（D6 + D7）
  ├── D6: 重复文本检测 + 质量评分
  ├── D6: manifest 质量字段 + 降权集成
  ├── D7: Citation Normalizer（统一引用合约）
  ├── D7: 后端预览 API
  └── D7: 前端预览面板

Phase 6 — 管理报告（D8 收尾）
  ├── D8: 管理后台 API
  ├── D8: 管理后台 UI
  └── 回归 Dashboard 展示
```

---

## 5. 文件清单

### 新增文件

| 路径 | 模块 | 职责 |
|---|---|---|
| `backend/core/project_query_intent.py` | D2 | Query Intent Classifier |
| `backend/core/project_query_ranking.py` | D2 | Ranking Adjuster |
| `backend/core/project_citation.py` | D7 | Citation Normalizer |
| `backend/core/project_source_metadata.py` | D2/D7 | Source Metadata Normalizer |
| `backend/core/project_quality_regression.py` | D1 | Regression Runner |
| `backend/core/project_quality_report.py` | D8 | Quality Report Gen |
| `backend/core/spreadsheet_preprocess.py` | D3 | Spreadsheet → Markdown |
| `backend/core/image_field_schemas.py` | D5 | Payment/Contact Sheet Fields |
| `backend/core/meeting_quality.py` | D6 | 重复检测 + 质量评分 |
| `backend/routers/project_preview.py` | D7 | 文件预览 API 端点 |
| `backend/skills/preprocessors/spreadsheet-preprocess/SKILL.md` | D3 | Skill 说明 |
| `backend/tests/test_project_query_intent.py` | D2 | 意图分类测试 |
| `backend/tests/test_project_query_ranking.py` | D2 | 排序测试 |
| `backend/tests/test_project_quality_regression.py` | D1 | 回归测试 |
| `backend/tests/test_project_quality_report.py` | D8 | 报告测试 |
| `backend/tests/test_spreadsheet_preprocess.py` | D3 | 表格预处理测试 |
| `backend/tests/test_image_field_schemas.py` | D5 | 图片字段测试 |
| `backend/tests/test_meeting_quality.py` | D6 | 会议质量测试 |
| `backend/tests/test_project_citation.py` | D7 | 引用合约测试 |
| `backend/tests/test_project_preview_api.py` | D7 | 预览 API 测试 |
| `backend/prompts/pdf-drawing-ga-v2.txt` | D4 | 图纸 GA prompt |
| `backend/prompts/pdf-drawing-ws-v1.txt` | D4 | 窗表 prompt |
| `backend/prompts/pdf-drawing-schedule-v1.txt` | D4 | 排期 prompt |
| `backend/prompts/pdf-drawing-sd-v1.txt` | D4 | Shop Drawing prompt |
| `backend/scripts/gbrain_project_quality_regression_query.py` | D1 | `--query` 模式入口 |
| `frontend/src/components/SourcePreviewPanel.tsx` | D7 | 预览面板 |
| `frontend/src/components/QualityReportCard.tsx` | D8 | 质量报告卡片 |

### 修改文件

| 路径 | 改动 |
|---|---|
| `backend/core/gbrain_project_ingest.py` | 集成 spreadsheet-preprocess；PDF 子分类；图片字段 schema |
| `backend/core/pdf_structured_extraction.py` | 子分类 prompt 路由；后处理校验 |
| `backend/core/image_structured_extraction.py` | Subkind detection；Extracted Fields 块输出 |
| `backend/core/extractor_classifier.py` | Spreadsheet → pending_capability → compiled（D3 完成后） |
| `backend/core/gbrain/_adapter.py` | `project_source_status` page_count/clone_state 修复 |
| `backend/core/gbrain_project_ingest.py` | 会议 manifest 增加 quality 字段（D6） |
| `backend/routers/project_query.py` | 集成 intent + ranking 层（D2） |
| `backend/core/gbrain/_adapter.py` | `query_project_source()` 增加 metadata 参数（D2） |
| `backend/tests/fixtures/gbrain_project_quality_regression_cases.json` | 新增字段 file_kind_hint, strict_checks（可选） |
| `frontend/src/.../chat/...` | 引用链接 → SourcePreviewPanel 打开 |

---

## 6. TEST 样本覆盖矩阵

| 样本文件 | file_kind | D1 fixture | D2 intent | D3/D4/D5 extract | D7 preview |
|---|---|---|---|---|---|
| `240704 Orama [Floor Plans].pdf` | `pdf_drawing` | ✅ test_floor_plan_l17 | ✅ 图纸 | ✅ D4 GA prompt | ✅ PDF page |
| `240715 Orama [WS].pdf` | `pdf_drawing` | ✅ test_window_schedule_w19 | ✅ 图纸/窗表 | ✅ D4 WS prompt | ✅ PDF page |
| `260205 Madeline [Facade Supply Programme] Rev04.pdf` | `pdf_schedule` | ✅ test_programme_duration + finish | ✅ 排期 | ✅ D4 Schedule prompt | ✅ PDF page |
| `邱智勇提交的内部联系单.pdf` | `pdf_drawing` | ✅ test_internal_contact_reason + items | ✅ 联系单 | ✅ D4 internal contact prompt | ✅ PDF page |
| `邱智勇提交的内部联系单_1.png` | `image` | ✅ test_internal_contact_reason | ✅ 联系单 | ✅ D5 ContactSheetFields | ✅ Image + region |
| `邱智勇提交的内部联系单_2.png` | `image` | ✅ test_internal_contact_items | ✅ 联系单 | ✅ D5 ContactSheetFields | ✅ Image + region |
| `20260529-...audio.docx` | `meeting_transcript_docx` | ✅ test_meeting_new_knowledge | ✅ 会议 | ✅ 现有 meeting extract | ✅ Text |
| `20260529-...audio.mp4` | `meeting_media` | ✅ test_meeting_new_knowledge (known_gap) | ✅ 会议 | ✅ 现有 transcription | ❌ Phase 5 |
| `2026-03-13 1551 RE-...eml` | `email` | ✅ test_email_skylight_glass | ✅ 邮件 | ✅ 现有 email extract | ✅ Email |
| `支付截图服务器.png` | `image` | ✅ test_payment_screenshot_amount | ✅ 支付截图 | ✅ D5 PaymentScreenshotFields | ✅ Image + region |
| `260506 ML (材料清单) Rev 01.xlsx` | `spreadsheet` | ✅ test_material_list_gl01 | ✅ 材料清单 | ✅ D3 spreadsheet-preprocess | ✅ Sheet table |
| `260506 注意事项 [BG0812] Rooster.docx` | `office_doc` | ✅ test_hardware_color_adaptation | ✅ 注意事项 | ✅ 现有 DOCX extract | ✅ Text |
| `20260529-...audio.auto.transcript.md` | `markdown` | — | — | ✅ 现有 markdown | ✅ Markdown |

---

## 7. 验收闸门

### Phase 1 闸门

- [ ] `python scripts/gbrain_project_quality_regression.py --query` 输出 14 题 JSON 报告
- [ ] 报告区分 pass / fail / known_gap / wrong_source / meeting_false_positive
- [ ] `project_source_status` 不再显示 `clone_state=corrupted`（回退为 `"available"`）
- [ ] 3 条 should_pass fixture（meeting_docx / email / office_doc）通过

### Phase 2 闸门

- [ ] "支付截图" query → intent.file_kind_hint = "image_payment"
- [ ] "L17 图纸" query → intent.file_kind_hint = "pdf_drawing"
- [ ] "GL01 玻璃" query → intent.file_kind_hint = "spreadsheet"
- [ ] 支付截图 query → 排序后支付截图页面排第一（非会议）

### Phase 3 闸门

- [ ] 支付截图 Markdown 含 `## Extracted Fields` → amount=68.00
- [ ] 内部联系单 PNG Markdown 含 `## Extracted Fields` → BG0806-LXD01
- [ ] 材料清单 XLSX manifest 状态 = `compiled`（不是 pending_extractor_capability）
- [ ] `GL01` 行出现在 gbrain-ready Markdown 中

### Phase 4 闸门

- [ ] 窗表 PDF gbrain-ready Markdown 含 W19 宽高 + 页码
- [ ] 排期 PDF gbrain-ready Markdown 含 L6-L39 Shop Drawing Duration + Finish
- [ ] 无索引字段时 `needs_review` 标记

### Phase 5 闸门

- [ ] 低质量转写可被检测并降权
- [ ] 非会议问题优先排除 poor/unusable 会议 source
- [ ] `GET /api/projects/{id}/preview/{path}` 返回正确预览 payload
- [ ] 前端引用点击打开预览面板

### Phase 6 闸门

- [ ] `GET /api/admin/quality/reports` 列出报告
- [ ] 管理后台显示 pass rate + known_gap 列表
- [ ] 14 题中 should_pass 全部通过（100%）

---

## 8. 风险和开放问题

| 风险 | 缓解 |
|---|---|
| PDF 图纸 MiMo V2.5 输出不稳定 | 后处理校验 + needs_review 标记，不编造 |
| XLSX 多 sheet/复杂格式不兼容 | 第一版聚焦材料清单类 XLSX，复杂格式继续 pending_capability |
| 会议 ASR 质量不可控 | 质量分类 + 降权可降低影响，不污染非会议查询 |
| GBrain ranking 不易外部调整 | Ranking Adjuster 在后端 post-process，不依赖 GBrain 内部排序 |
| 预览 API 大文件性能 | PDF/图片直接返回原始文件 URL，不做转码 |
| 管理报告数据膨胀 | 每次运行覆盖同项目最新报告，不累积历史版本 |

**开放问题**:

1. 图纸 PDF 的 MiMo V2.5 提取结果是否需要人工审核后再入 GBrain？建议：pending_review → 但 8.D 第一版不做阻塞式审核，结果先入 GBrain 并标记 needs_review

2. 预览面板是否在项目工作区右侧常驻？建议：复用现有右侧工具面板，新增 tab
