import type { KnowledgeReviewDraftResponse, KnowledgeReviewResponse } from "../../../../shared/api/types";
import {
  buildReviewDiffSummary,
  canSubmitCitationFixer,
  getDraftContent,
  isPendingReview,
  reviewSourceLabel,
  summarizeKnowledgeReview,
  type KnowledgeReviewDrafts,
} from "./knowledgeReviewView";

export type KnowledgeReviewDetailProps = {
  adminLoading: boolean;
  drafts: KnowledgeReviewDrafts;
  formatDate: (value: string | number) => string;
  item: KnowledgeReviewResponse | null;
  onDraftChange: (item: KnowledgeReviewResponse, value: string) => void;
  onGenerateDraft: (item: KnowledgeReviewResponse) => Promise<KnowledgeReviewDraftResponse | null>;
  onReview: (item: KnowledgeReviewResponse, status: "approved" | "rejected", content?: string) => Promise<boolean>;
  onSubmitCitationFixer: (item: KnowledgeReviewResponse) => Promise<void>;
};

export function KnowledgeReviewDetail({
  adminLoading,
  drafts,
  formatDate,
  item,
  onDraftChange,
  onGenerateDraft,
  onReview,
  onSubmitCitationFixer,
}: KnowledgeReviewDetailProps) {
  if (!item) {
    return (
      <aside className="admin-knowledge-review-detail">
        <p className="admin-knowledge-review-empty">请选择一条审核项查看详情。</p>
      </aside>
    );
  }

  const activeItem = item;
  const draft = getDraftContent(item, drafts);
  const diff = buildReviewDiffSummary(item.content, draft);
  const canApprove = isPendingReview(item) && Boolean(draft.trim());
  const canReject = isPendingReview(item);
  const gbrainSummary = summarizeKnowledgeReview(item);
  async function handleGenerateDraft() {
    const result = await onGenerateDraft(activeItem);
    if (result?.draft) {
      onDraftChange(activeItem, result.draft);
    }
  }

  return (
    <aside className="admin-knowledge-review-detail">
      <header className="admin-knowledge-review-detail-header">
        <div>
          <strong>#{item.id} {reviewSourceLabel(item)}</strong>
          <span>{item.source || "候选知识"} · {formatDate(item.created_at)}</span>
        </div>
        <span className={`admin-knowledge-review-status is-${item.status}`}>{item.status}</span>
      </header>

      {gbrainSummary ? (
        <>
          <section className="admin-knowledge-review-card is-user-supplement">
            <span className="admin-knowledge-review-eyebrow">缺口主题</span>
            <strong>{gbrainSummary.topic}</strong>
            <p>{gbrainSummary.adminSummary}</p>
            {gbrainSummary.userNote ? (
              <div className="admin-knowledge-review-supplement-item">
                <span>用户补充说明</span>
                <p>{gbrainSummary.userNote}</p>
              </div>
            ) : null}
          </section>

          <section className="admin-knowledge-review-card">
            <div className="admin-knowledge-review-field-header">
              <strong>审核后知识</strong>
              <div>
                <span>通过前必填</span>
                <button
                  className="ghost-button admin-knowledge-review-draft-button"
                  disabled={adminLoading || !isPendingReview(item)}
                  onClick={() => void handleGenerateDraft()}
                  type="button"
                >
                  生成审核草稿
                </button>
              </div>
            </div>
            <p>请写入可长期复用的正式知识，不要复制原始 GBrain 诊断、trace、gap/conflict/warning 文本。</p>
            <textarea
              className="admin-knowledge-review-clean-draft"
              disabled={adminLoading || !isPendingReview(item)}
              onChange={(event) => onDraftChange(item, event.target.value)}
              placeholder={"例如：\n## 知识主题\n当出现某类业务场景时，应如何判断和处理...\n\n## 适用场景\n...\n\n## 处理原则\n1. ...\n2. ..."}
              value={draft}
            />
            <div className={`admin-knowledge-review-diff-note is-${diff.tone}`}>
              {diff.text}
            </div>
          </section>

          <details className="admin-knowledge-review-raw">
            <summary>系统证据</summary>
            <section>
              <strong>用户原问题</strong>
              <p>{gbrainSummary.question || "未记录用户原始问题。"}</p>
            </section>
            <section>
              <strong>GBrain 判断</strong>
              <IssueGroup label="知识缺口" items={gbrainSummary.gaps} empty="未发现明确知识缺口。" />
              <IssueGroup label="知识冲突" items={gbrainSummary.conflicts} empty="未发现明确知识冲突。" />
              <IssueGroup label="风险提示" items={gbrainSummary.warnings} empty="未发现明确风险提示。" />
            </section>
            {gbrainSummary.citations.length ? (
              <section>
                <strong>引用来源</strong>
                <div className="admin-knowledge-review-pills" aria-label="引用来源">
                  {gbrainSummary.citations.map((citation) => <span key={citation}>{citation}</span>)}
                </div>
              </section>
            ) : null}
            <section>
              <strong>原始审计 content</strong>
            </section>
            <pre>{item.content || "空内容"}</pre>
          </details>
        </>
      ) : (
        <>
          <div className={`admin-knowledge-review-diff-note is-${diff.tone}`}>
            {diff.text}
          </div>

          <div className="admin-knowledge-review-diff">
            <section>
              <strong>原审核内容</strong>
              <pre>{item.content || "空内容"}</pre>
            </section>
            <section>
              <strong>本次编辑草稿</strong>
              <textarea
                disabled={adminLoading || !isPendingReview(item)}
                onChange={(event) => onDraftChange(item, event.target.value)}
                value={draft}
              />
            </section>
          </div>
        </>
      )}

      <div className="admin-knowledge-review-detail-actions">
        {canSubmitCitationFixer(item) ? (
          <button className="ghost-button" disabled={adminLoading} onClick={() => void onSubmitCitationFixer(item)} type="button">
            引用修复
          </button>
        ) : null}
        <button
          className="ghost-button"
          disabled={adminLoading || !canApprove}
          onClick={() => void onReview(item, "approved", draft)}
          type="button"
        >
          通过
        </button>
        <button
          className="ghost-button"
          disabled={adminLoading || !canReject}
          onClick={() => void onReview(item, "rejected")}
          type="button"
        >
          驳回
        </button>
      </div>
    </aside>
  );
}

function IssueGroup({ empty, items, label }: { empty: string; items: string[]; label: string }) {
  return (
    <div className="admin-knowledge-review-issue-group">
      <span>{label}</span>
      {items.length ? (
        <ul>
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </div>
  );
}
