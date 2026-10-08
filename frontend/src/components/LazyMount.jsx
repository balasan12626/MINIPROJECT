import { useEffect, useRef, useState } from "react";

/** Mounts `children` only once the placeholder scrolls near the viewport.
 *
 * `minHeight` reserves space so mounting causes no layout shift. With
 * `keepMounted` (default) the subtree stays mounted after first view; pass
 * `onVisibleChange` to pause polling/animation while off-screen. */
export default function LazyMount({ children, minHeight = 320, rootMargin = "300px 0px", keepMounted = true, onVisibleChange, className }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);
  const cbRef = useRef(onVisibleChange);
  cbRef.current = onVisibleChange;

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      setMounted(true);
      return undefined;
    }
    const io = new IntersectionObserver(([entry]) => {
      const v = entry.isIntersecting;
      setVisible(v);
      if (v) setMounted(true);
      cbRef.current?.(v);
    }, { rootMargin });
    io.observe(el);
    return () => io.disconnect();
  }, [rootMargin]);

  const show = keepMounted ? mounted : visible;
  return (
    <div ref={ref} className={className} style={show ? undefined : { minHeight }} data-lazy-visible={visible ? "1" : "0"}>
      {show ? children : null}
    </div>
  );
}
