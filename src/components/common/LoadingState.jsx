export default function LoadingState({ label = "불러오는 중입니다." }) {
  return (
    <section className="state-panel" role="status" aria-live="polite" aria-busy="true">
      <div className="state-panel__content">
        <span className="loading-spinner" aria-hidden="true" />
        <p className="state-panel__description">{label}</p>
      </div>
    </section>
  );
}
