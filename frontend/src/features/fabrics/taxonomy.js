import { useEffect, useState } from 'react';
import { api } from '../../services/api';

export const emptyClassification = () => ({ kind: '', variant: '', placements: [] });

export function useFabricTaxonomy() {
  const [taxonomy, setTaxonomy] = useState(null);
  useEffect(() => {
    let live = true;
    api.getInventoryTaxonomy()
      .then((data) => { if (live) setTaxonomy(data); })
      .catch(() => { if (live) setTaxonomy({ kinds: [], slots: [], garments: [] }); });
    return () => { live = false; };
  }, []);
  return taxonomy;
}

