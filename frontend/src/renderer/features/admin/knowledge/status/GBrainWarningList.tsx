import type { GBrainWarningItem } from "./gbrainStatusTypes";

export type GBrainWarningListProps = {
  warnings: GBrainWarningItem[];
};

export function GBrainWarningList({ warnings }: GBrainWarningListProps) {
  return (
    <section className="admin-gbrain-status-section">
      <header>
        <strong>Warnings & Actions</strong>
        <span>{warnings.length ? `${warnings.length} 条需要处理或关注` : "暂无明确 warning"}</span>
      </header>
      {warnings.length ? (
        <div className="admin-gbrain-status-warning-list">
          {warnings.map((item) => (
            <article className={`admin-gbrain-status-warning is-${item.level}`} key={item.id}>
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
              <span>{item.action}</span>
            </article>
          ))}
        </div>
      ) : (
        <p className="admin-gbrain-status-empty">关键状态源未返回需要处理的问题。</p>
      )}
    </section>
  );
}
