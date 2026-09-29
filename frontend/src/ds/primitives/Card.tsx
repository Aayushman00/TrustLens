import type { ReactNode } from "react";

/** Structural chrome. Not a data layer — use Slip for evidence. */
export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="tl-card">
      {(title || actions) && (
        <header className="tl-card__head">
          {title && <h3 className="tl-card__title">{title}</h3>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

/** Evidence material: hairline "specimen paper". Never takes score colours. */
export function Slip({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="tl-slip">
      {label && <div className="tl-slip__label">{label}</div>}
      {children}
    </div>
  );
}
