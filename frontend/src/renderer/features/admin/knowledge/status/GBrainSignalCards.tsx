import type { GBrainSignalCard } from "./gbrainStatusTypes";

export type GBrainSignalCardsProps = {
  signals: GBrainSignalCard[];
};

export function GBrainSignalCards({ signals }: GBrainSignalCardsProps) {
  return (
    <section className="admin-gbrain-status-section">
      <header>
        <strong>Key Signals</strong>
        <span>doctor / worker / jobs / quality</span>
      </header>
      <div className="admin-gbrain-status-signal-grid">
        {signals.map((signal) => (
          <article className={`admin-gbrain-status-signal is-${signal.status}`} key={signal.id}>
            <span>{signal.label}</span>
            <strong>{signal.value}</strong>
            <p>{signal.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
