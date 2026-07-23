export default function Tag({ children, tone = "default", onRemove, removeLabel, className = "" }) {
  const classes = ["tag", tone !== "default" && `tag--${tone}`, className].filter(Boolean).join(" ");
  return (
    <span className={classes}>
      <span className="tag__label">{children}</span>
      {onRemove && (
        <button className="tag__remove" type="button" onClick={onRemove} aria-label={removeLabel || `${children} 태그 삭제`}>
          <span aria-hidden="true">×</span>
        </button>
      )}
    </span>
  );
}
