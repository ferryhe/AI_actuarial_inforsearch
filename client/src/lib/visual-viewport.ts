export function watchVisualViewport(update: (top: number, bottom: number) => void) {
  const viewport = window.visualViewport;
  const sync = () => {
    const top = viewport?.offsetTop ?? 0;
    update(top, top + (viewport?.height ?? window.innerHeight));
  };

  sync();
  window.addEventListener("resize", sync);
  viewport?.addEventListener("resize", sync);
  viewport?.addEventListener("scroll", sync);
  return () => {
    window.removeEventListener("resize", sync);
    viewport?.removeEventListener("resize", sync);
    viewport?.removeEventListener("scroll", sync);
  };
}
