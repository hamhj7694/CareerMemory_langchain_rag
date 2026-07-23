export default function EmptyState({ title, description, actionLabel, onAction, icon = "○" }) {
  return (
    <section className="state-panel">
      <div className="state-panel__content">
        <span className="state-panel__icon" aria-hidden="true">{icon}</span>
        <h2 className="state-panel__title">{title}</h2>
        {description && <p className="state-panel__description">{description}</p>}
        {actionLabel && onAction && <button className="ui-button" type="button" onClick={onAction}>{actionLabel}</button>}
      </div>
    </section>
  );
}
