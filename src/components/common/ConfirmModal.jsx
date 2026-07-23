import { useEffect, useId, useRef } from "react";

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function ConfirmModal({ open, title, children, confirmLabel = "확인", cancelLabel = "취소", tone = "primary", onConfirm, onCancel }) {
  const titleId = useId();
  const bodyId = useId();
  const dialogRef = useRef(null);
  const confirmRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    confirmRef.current?.focus();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") { event.preventDefault(); onCancel?.(); return; }
      if (event.key !== "Tab") return;
      const focusable = [...dialogRef.current.querySelectorAll(FOCUSABLE)];
      if (!focusable.length) { event.preventDefault(); return; }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = originalOverflow;
      previousFocus?.focus?.();
    };
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel?.(); }}>
      <section ref={dialogRef} className="modal" role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={bodyId}>
        <header className="modal__header"><h2 className="modal__title" id={titleId}>{title}</h2></header>
        <div className="modal__body" id={bodyId}>{children}</div>
        <footer className="modal__actions">
          <button className="ui-button ui-button--secondary" type="button" onClick={onCancel}>{cancelLabel}</button>
          <button ref={confirmRef} className={`ui-button${tone === "danger" ? " ui-button--danger" : ""}`} type="button" onClick={onConfirm}>{confirmLabel}</button>
        </footer>
      </section>
    </div>
  );
}
