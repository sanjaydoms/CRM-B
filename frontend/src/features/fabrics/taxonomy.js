import { useEffect, useState } from 'react';
import { api } from '../../services/api';

export const emptyClassification = () => ({ kind: '', variant: '', placements: [] });

export function useFabricTaxonomy() {
  const [taxonomy, setTaxonomy] = useState(null);
  useEffect(() => {
    let live = true;
    api.getFabricTaxonomy()
      .then((data) => { if (live) setTaxonomy(data); })
      .catch(() => { if (live) setTaxonomy({ kinds: [], slots: [], garments: [] }); });
    return () => { live = false; };
  }, []);
  return taxonomy;
}

let nextRowId = 0;

// _id keeps React's key stable so a row's local UI state doesn't shift onto
// its neighbour when one is removed.

/** One saleable fabric: its own details and photos. */
export const blankMaterial = () => ({
  _id: ++nextRowId,
  name: '',
  material: '',
  color: '',
  color_hex: '#c8a97e',
  price_per_meter: '',
  image_url: '',
  image_urls: [],
  is_available: true,
});

/** One placement (Saree > Pallu, or an accessory) plus every material for it. */
export const blankGroup = () => ({
  _id: ++nextRowId,
  ...emptyClassification(),
  materials: [blankMaterial()],
});
