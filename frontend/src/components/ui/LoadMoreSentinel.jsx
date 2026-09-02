import { useEffect, useRef } from 'react';

/**
 * An invisible row at the bottom of a list that asks for the next page when it
 * scrolls into view.
 *
 * IntersectionObserver rather than a scroll handler: a scroll listener fires
 * on every pixel and has to measure the document to decide anything, which on
 * a phone is the jank you feel when a long list stutters. This fires once,
 * when the bottom of the list actually approaches, and costs nothing while it
 * does not.
 *
 * `rootMargin` starts the fetch 400px early, so on a normal scroll the next
 * page has usually arrived before the reader reaches the end and the list does
 * not visibly stop.
 */
export function LoadMoreSentinel({ onVisible, disabled = false }) {
  const ref = useRef(null);

  useEffect(() => {
    if (disabled || !ref.current) return undefined;
    // Not available in very old WebViews; without it the list simply stops at
    // the pages already loaded rather than breaking.
    if (typeof IntersectionObserver === 'undefined') return undefined;

    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) onVisible();
    }, { rootMargin: '400px' });

    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [onVisible, disabled]);

  return <div ref={ref} aria-hidden="true" style={{ height: '1px' }} />;
}
