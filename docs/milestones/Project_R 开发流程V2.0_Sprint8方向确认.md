



## 结论：我建议做“方案 1.5”，不是纯方案 1，也不是完整方案 2

你的判断是对的：**Sprint 8 应先做可验证 MVP**。但我不建议只做“简单筛选 + 状态说明”，因为这容易变成一个很弱的 UI 小补丁。更合理的方向是：

> **Sprint 8 做“本轮回答的 Evidence UX / 证据解释体验”，让用户能判断：这次回答用了什么来源、这些来源属于什么范围、有没有风险、我是否需要进一步核对。**

也就是说，Sprint 8 不应该做“知识库浏览器”，而应该做“答案证据解释层”。

这与 Project_R V2.0 的边界一致：GBrain 的目标是让普通用户看懂本次查询范围、引用来源、定位和限制，而知识库元数据、source 列表、入库状态和质量报告应面向有权限的管理员 fileciteturn2file0。你的计划里也明确写了普通用户不展示全量 source、目录、chunk、入库状态，只展示本轮引用来源预览和范围解释 fileciteturn2file0。

---

## 一、市面成熟产品可以吸收什么

### 1. Glean：引用不是“摆链接”，而是帮助用户验证判断

Glean 的 Citation 设计重点不是展示越多 source 越好，而是让用户知道某个回答依据了哪些文档、文件、人员记录，并可通过预览、上下文、高亮文本、页码等方式确认来源是否正确；同时它强调 citation 不会绕过权限，用户只能打开自己有权限访问的内容。citeturn870844view1

**可吸收点：**

- 来源应该跟回答语句绑定，而不是只放一个杂乱来源列表。
- 来源预览要展示“为什么引用它”：命中片段、上下文、页码/行号/定位。
- 权限边界要始终保持：普通用户不能因为回答来源而获得额外知识库访问权。
- Source 状态解释应围绕“本轮回答可验证性”，不是展示后台治理数据。

对你来说，这意味着 G4 不应叫“Source 状态用户可见”，更准确应改成：

> **本轮引用可信度提示 / Evidence Status Explanation**

---

### 2. Glean AI Answers：企业知识问答核心是“权限感知 + 可验证”

Glean AI Answers 明确强调回答来自组织文档，并带具体引用以保证透明和可验证；同时生成回答只使用用户有权限访问的内容。citeturn870844view2

**可吸收点：**

- 用户侧重点不是“我能不能翻知识库”，而是“这次答案是否可验证”。
- 权限感知要成为 UI 文案的一部分，例如：  
  “仅基于你当前有权限访问的项目资料生成。”
- 需要明确提示当前查询是否覆盖了公司库、项目库、客户库、外部来源。

对 Project_R 来说，这一点非常重要，因为你的系统有 **company-wiki / project source / customer intelligence** 三类 scope。Sprint 8 可以把“范围透明”做成产品信任基础。

---

### 3. NotebookLM：用户选择来源子集，而不是浏览整个知识库

NotebookLM 的机制是：Sources 总是用于回答，但可以是全部来源或用户选中的子集；如果来源内容太短，可能不会给到具体引用，而是引用整个文档。citeturn870844view3

**可吸收点：**

- “来源筛选”可以不是复杂搜索过滤器，而是简单的 **source subset 控制**。
- 对普通用户来说，筛选入口应是“本轮回答范围选择”，不是“知识库管理”。
- 当系统无法给出精确页码/行号时，需要明确说明“定位精度有限”。

这对你的 Sprint 8 很有价值：G3 不应该做复杂的全局检索过滤，而应该做 **本轮结果来源范围筛选**。

---

### 4. Microsoft Copilot Studio：知识源有层级和优先级

Copilot Studio 的 generative answers 可以使用内部或外部知识源，也支持 agent-level source 和 topic-level source；topic-level knowledge source 会优先于 agent-level source，agent-level source 作为 fallback。citeturn870844view0turn870844view5

**可吸收点：**

- 来源范围不只是分类，还应有“优先级解释”。
- 比如当前项目查询时：  
  **当前项目资料优先，公司知识作为补充，不混入其他项目资料。**
- 客户工作区则应提示：  
  **仅查询当前客户情报，不叠加公司库或项目库。**

这正好对应你已有的 workspace source scope 逻辑。

---

### 5. Perplexity：搜索型产品重视过滤、排序、引用，但这不等于企业知识库浏览

Perplexity API 平台强调 real-time web search、ranked results、domain filtering、multi-query search、content extraction，以及带引用的 grounded answers。citeturn870844view4

**可吸收点：**

- “过滤”最有价值的是让用户理解结果来源边界，例如内部/外部、公司/项目/客户、官方/非官方。
- 但 Project_R 不是公网搜索引擎，不应照搬 Perplexity 的开放式 source exploration。
- 你更需要的是“受控范围内的证据过滤”。

---

### 6. 研究层面的提醒：有引用不等于可信

一项关于 answer engine 的研究指出，带引用的生成式搜索仍存在幻觉和不准确 citation 等问题；另一项 2026 年研究发现，多个生成式搜索系统中存在引用 AI 生成来源的风险，约 16% cited sources 显示出 AI-generated source 的迹象。citeturn342660view0turn342660view2

**可吸收点：**

- 不要把“有来源”包装成“答案一定正确”。
- Source 状态说明应使用谨慎语言，例如：
  - “本回答有可追溯来源”
  - “部分结论缺少直接来源支持”
  - “不同来源存在冲突”
  - “该来源定位精度有限”
- 不建议在 Sprint 8 做绝对化的“可信度评分”，否则容易给用户错误安全感。

---

## 二、建议采用的 Sprint 8 产品方向

我建议把 Sprint 8 改成：

# Sprint 8 · GBrain 用户侧证据解释增强

核心目标：

> 用户看完 GBrain 回答后，能快速判断：  
> **这次回答查了哪些范围、引用了哪些证据、哪些地方需要谨慎、下一步该怎么核对。**

不是做：

> 普通用户知识库浏览器 / source 管理器 / chunk 浏览器 / 管理员状态面板。

---

## 三、推荐功能拆分

### G3：结果来源过滤，不是“知识库过滤器”

建议做成回答来源区顶部的 Filter Chips：

| 筛选项 | 作用 |
|---|---|
| 全部 | 显示本轮全部引用来源 |
| 公司知识 | 只看 company-wiki 引用 |
| 项目资料 | 只看当前项目 source 引用 |
| 客户情报 | 只看当前客户情报引用 |
| 外部来源 | 如果本轮有外部来源才显示 |
| 有风险提示 | 只看带 gap / conflict / warning 的来源 |

重点：  
这个筛选只作用于 **本轮回答 sources**，不触发全量知识库检索，不暴露 source 目录。

UI 文案建议：

> 筛选仅影响本轮引用来源展示，不会浏览完整知识库。

---

### G4：Source 状态用户可见，应改为“本轮引用状态解释”

不要直接展示：

- rag_status 原始值
- chunk 状态
- 入库状态
- embedding 状态
- 索引任务状态
- 后台质量报告

普通用户只需要看到这些解释：

| 状态 | 用户侧展示 |
|---|---|
| 本轮引用 | “该来源已被本次回答引用” |
| 定位完整 | “可定位到页码 / 行号 / 文件片段” |
| 定位有限 | “仅能定位到文件级，无法定位到具体页/行” |
| 来源范围 | “来自当前项目资料 / 公司知识 / 客户情报” |
| 时间风险 | “该文件可能不是最新版本，请核对文件日期” |
| gap | “回答中存在资料缺口” |
| conflict | “不同来源存在冲突” |
| warning | “系统对该引用有风险提示” |

更适合的命名：

> **Source Status Explanation Panel**  
> 或中文：**来源解释面板 / 证据说明面板**

---

## 四、我建议的最终方案：方案 1.5

### 方案 1.5 = 前端 MVP + 极小数据归一化，不新增复杂后端治理接口

你现在已有：

- `message.sources`
- `context_trace.gbrain_think`
- `source_file/source_page/source_line/source_locator`
- `workspaceFilePanelUtils.ts` 的 `getRagStatusMeta`
- `sourcePreview.ts`
- `MessageSourceList.tsx`
- `SourcePreviewPanel.tsx`

所以 Sprint 8 不需要大后端。但建议加一个**前端 normalization 层**，不要让 UI 组件直接到处推断 source 类型。

建议新增：

```text
frontend/src/renderer/features/knowledge/sourceEvidence.ts
frontend/src/renderer/features/knowledge/sourceEvidenceTypes.ts
frontend/src/renderer/features/knowledge/components/SourceEvidenceSummary.tsx
frontend/src/renderer/features/knowledge/components/SourceEvidenceFilters.tsx
frontend/src/renderer/features/knowledge/components/SourceEvidencePanel.tsx
```

其中 `sourceEvidence.ts` 负责把现有字段归一化为：

```ts
type SourceEvidence = {
  id: string
  title: string
  kind: 'company' | 'project' | 'customer' | 'external' | 'unknown'
  scopeLabel: string
  locatorLabel?: string
  fileName?: string
  page?: number
  line?: number
  excerpt?: string
  isCitedInThisAnswer: boolean
  statusLevel: 'normal' | 'limited' | 'warning' | 'conflict' | 'gap'
  statusText: string
  limitations: string[]
}
```

这样后续如果进入方案 2，后端补 `source_kind/status_hint`，前端只改 normalization，不用大改 UI。

---

## 五、Sprint 8 不建议做什么

### 1. 不做普通用户知识库浏览器

这会冲突你 V2.0 已经确定的边界：普通用户只看来源范围和本轮引用片段，不能看到 source 列表、知识库目录和入库状态 fileciteturn2file0。

### 2. 不做管理员 source 状态列表

这个应留到 Sprint 9。否则 Sprint 8 会变成“用户侧 + 管理侧”混合，范围失控。

### 3. 不做复杂可信度评分

不要显示：

> 可信度 87%

这类数字看起来高级，但如果没有严谨算法和测试，很容易误导用户。建议只做状态标签：

- 正常引用
- 定位有限
- 资料缺口
- 来源冲突
- 需要核对

### 4. 不做全量 source 搜索

G3 的“过滤”只过滤本轮 sources，不查全库。

---

## 六、建议的 Sprint 8 验收标准

### 用户侧验收

完成后，用户在一条 GBrain 回答里应能看到：

1. 本次查询了哪些范围。
2. 本次没有查询哪些范围。
3. 回答实际引用了哪些来源。
4. 每个来源属于公司 / 项目 / 客户 / 外部哪一类。
5. 每个来源能否定位到页码、行号或片段。
6. 是否存在 gap / conflict / warning。
7. 筛选后如果没有对应来源，应显示清晰空状态。

示例空状态：

> 本轮回答未引用“客户情报”来源。  
> 这不代表客户情报库中没有相关资料，只代表本次回答没有使用该类来源。

---

## 七、建议给 Codex / AI Agent 的执行指令

可以这样下达任务：

```text
Sprint 8 采用 GBrain Evidence UX 方向，不做普通用户知识库浏览器，不做管理员 source 管理列表。

目标：
基于现有 message.sources 与 context_trace.gbrain_think，为普通用户增强“本轮回答来源解释”。

实现范围：
1. 在 features/knowledge 下新增 sourceEvidence normalization 层，将现有 source 字段归一化为 SourceEvidence。
2. 在 MessageSourceList / SourcePreviewPanel 的基础上增加来源类型筛选：
   - All
   - Company Knowledge
   - Project Sources
   - Customer Intelligence
   - External Sources
   - Issues / Warnings
3. Source Preview 中增加 Evidence Explanation 区块：
   - source kind / scope
   - locator: file/page/line/source_locator
   - limitation text
   - gap/conflict/warning summary from context_trace
4. 所有筛选只作用于本轮 message.sources，不请求全量 source，不展示 chunk，不展示入库状态列表。
5. 普通用户不得看到 raw rag_status、embedding status、admin quality report。
6. 如需根据路径推断 source_kind，集中写在 sourceEvidence.ts，不要散落在组件中。
7. 保持后续兼容：如果后端未来补 source_kind/status_hint，只需替换 normalization 逻辑。

验收：
- bun run typecheck
- Playwright 覆盖：
  a. sources 可按类型筛选
  b. 无对应来源时显示空状态
  c. gap/conflict/warning 可在来源解释中看到
  d. 普通用户无法进入全量 source / 知识库目录 / 入库状态列表
```

---

## 八、最终判断

我不建议选原始方案 2，因为现在补后端字段会把 Sprint 8 拉大；也不建议选原始方案 1 的“轻 UI”，因为产品价值可能不够明显。

最佳选择是：

> **方案 1.5：前端竖切片为主，建立 SourceEvidence 归一化层，做本轮回答的来源过滤、证据解释、风险提示；后端字段增强留接口位，但不在本轮强做。**

这样 Sprint 8 既能快速闭环，又能吸收成熟产品的核心思路：**citation-forward、permission-aware、scope-aware、limitation-aware**。这比做一个普通知识库浏览器更符合 Project_R 当前阶段。