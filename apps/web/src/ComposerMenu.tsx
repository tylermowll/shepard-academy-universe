import { useEffect, useRef, type ReactNode } from "react";

/** A disclosure with native exclusive-open behavior and predictable dismissal. */
export function ComposerMenu({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  const menu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (
        menu.current &&
        event.target instanceof Node &&
        !menu.current.contains(event.target)
      )
        menu.current.open = false;
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && menu.current?.open) {
        menu.current.open = false;
        menu.current.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  return (
    <details
      ref={menu}
      name="tutor-composer"
      className={`composer-menu ${className}`}
      onClick={(event) => {
        if (
          event.target instanceof Element &&
          event.target.closest("button:not(:disabled)")
        ) {
          event.currentTarget.open = false;
          event.currentTarget.querySelector("summary")?.focus();
        }
      }}
    >
      <summary>{title}</summary>
      {children}
    </details>
  );
}
