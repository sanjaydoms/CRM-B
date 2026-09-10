import { useEffect, useState } from 'react';

import { api } from '../../services/api';
import GarmentSummary from './GarmentSummary';

/**
 * "What to make", for a garment that has already been ordered.
 *
 * A saved GarmentJob holds its answers (`spec`, `measurements`) and its
 * material lines, but not the template that gives those answers their
 * sections, labels and option names. This fetches each template once and hands
 * GarmentSummary the same shape the wizard gives it, so the stage panel reads
 * exactly like the review the owner approved -- grouped, labelled, in order.
 *
 * If a template cannot be read, the answers are still shown, grouped by the
 * two things the row itself knows: measurements and everything else.
 */

const fallbackTemplate = (job) => ({
  name: job.template_name || job.template_key || 'Custom garment',
  sections: [
    {
      key: 'measurements', title: 'Measurements',
      fields: Object.keys(job.measurements || {}).map((key) => ({ key, field_type: 'number', unit: 'in' })),
    },
    {
      key: 'details', title: 'Details',
      fields: Object.keys(job.spec || {}).map((key) => ({ key, field_type: 'text' })),
    },
  ],
});

export default function OrderGarmentBrief({ jobs, specialInstructions }) {
  const [templates, setTemplates] = useState({});

  const keys = [...new Set((jobs || []).map((j) => j.template_key).filter(Boolean))];
  const wanted = keys.join(',');

  useEffect(() => {
    let cancelled = false;
    keys.forEach((key) => {
      if (templates[key] !== undefined) return;
      api.getGarmentTemplate(key)
        .then((tpl) => { if (!cancelled) setTemplates((t) => ({ ...t, [key]: tpl })); })
        .catch(() => { if (!cancelled) setTemplates((t) => ({ ...t, [key]: null })); });
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted]);

  // Material lines carry the item's name, quantity and unit; the spec holds
  // only the item id. The name map lets GarmentSummary print "Raw silk · 2.5 m"
  // where it would otherwise print a UUID, and a customer's own cloth is named
  // the way it was written down at the counter.
  const inventoryNames = {};
  const shaped = (jobs || []).map((job) => {
    const values = { ...(job.spec || {}), ...(job.measurements || {}) };
    (job.materials || []).forEach((line) => {
      const qty = Number(line.quantity) > 0 ? ` · ${Number(line.quantity)} ${line.unit || ''}`.trimEnd() : '';
      if (line.inventory_item) {
        inventoryNames[String(line.inventory_item)] = `${line.item_name || 'Stock item'}${qty}`;
        values[line.field_key] = line.inventory_item;
      } else if (line.free_text) {
        const token = `customer:${line.id}`;
        inventoryNames[token] = `${line.free_text} (customer's own)${qty}`;
        values[line.field_key] = token;
      }
    });
    const template = templates[job.template_key] || fallbackTemplate(job);
    return { key: job.id, template, values };
  });

  const loading = keys.some((key) => templates[key] === undefined);

  return (
    <div className="garment-brief">
      <div className="garment-brief-head">
        <span className="ui-eyebrow">What to make</span>
        {loading && <span className="ui-badge ui-badge--neutral">Loading details…</span>}
      </div>
      <GarmentSummary jobs={shaped} inventoryNames={inventoryNames} />
      {specialInstructions && (
        <div className="garment-instructions">
          <div className="ui-eyebrow garment-section-title">Special instructions</div>
          <div className="garment-instructions-text">{specialInstructions}</div>
        </div>
      )}
    </div>
  );
}
