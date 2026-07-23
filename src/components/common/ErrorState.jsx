export default function ErrorState({ title = "문제가 발생했습니다", description, onRetry, retryLabel = "다시 시도" }) {
  return (
    <section className="state-panel state-panel--error" role="alert">
      <div className="state-panel__content">
        <span className="state-panel__icon" aria-hidden="true">!</span>
        <h2 className="state-panel__title">{title}</h2>
        {description && <p className="state-panel__description">{description}</p>}
        {onRetry && <button className="ui-button" type="button" onClick={onRetry}>{retryLabel}</button>}
      </div>
    </section>
  );
}
