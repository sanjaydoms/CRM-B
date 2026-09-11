import { useEffect, useState } from 'react';

import { api } from '../../services/api';

/** The design catalogue tree for one garment, fetched once per garment for
 *  the life of the page -- it is boutique-wide configuration, not screen data.
 *
 *  A garment with no catalogue resolves to `{categories: []}`, which is what
 *  every garment other than the saree is today, and which the callers render
 *  as nothing at all.
 */
const cache = new Map();
const EMPTY = { categories: [] };

export function useDesignCatalogue(garmentKey) {
  // Stamped with the garment it answers, so a switch to a cached garment is
  // read straight from the cache on render rather than set from an effect.
  const [loaded, setLoaded] = useState(null);

  useEffect(() => {
    if (!garmentKey || cache.has(garmentKey)) return undefined;
    let cancelled = false;
    api.getDesignCatalogue(garmentKey)
      .then((tree) => { cache.set(garmentKey, tree || EMPTY); if (!cancelled) setLoaded({ garmentKey, tree: tree || EMPTY }); })
      .catch(() => { cache.set(garmentKey, EMPTY); if (!cancelled) setLoaded({ garmentKey, tree: EMPTY }); });
    return () => { cancelled = true; };
  }, [garmentKey]);

  if (!garmentKey) return null;
  if (cache.has(garmentKey)) return cache.get(garmentKey);
  return loaded?.garmentKey === garmentKey ? loaded.tree : null;
}

/** The labels along a path, for a caption: "Traditional … › Silk / Pattu › Banarasi Silk". */
export function describePath(tree, value) {
  const cat = (tree?.categories || []).find((c) => c.key === value?.category);
  if (!cat) return '';
  const sub = (cat.subcategories || []).find((s) => s.key === value?.subcategory);
  const options = sub ? sub.options : (cat.options || []);
  const opt = options.find((o) => o.key === value?.option);
  return [cat.label, sub?.label, opt?.label].filter(Boolean).join(' › ');
}

/** The position to send for a chosen path, or null while the choice is
 *  incomplete -- so a half-chosen path is never posted and refused. */
export function cataloguePayload(tree, value) {
  const cat = (tree?.categories || []).find((c) => c.key === value?.category);
  if (!cat) return null;
  const sub = (cat.subcategories || []).find((s) => s.key === value?.subcategory);
  if (cat.subcategories && !sub) return null;
  const options = sub ? sub.options : (cat.options || []);
  if (options.length > 0 && !options.some((o) => o.key === value?.option)) return null;
  return { category: cat.key, subcategory: sub?.key || '', option: options.length ? value.option : '' };
}
