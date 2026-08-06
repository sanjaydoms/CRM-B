import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

export function ProgressiveAccordion({ title, subtitle, icon: Icon, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`progressive-accordion-card ${open ? 'open' : ''}`}>
      <button
        type="button"
        className="accordion-header-btn"
        onClick={() => setOpen(!open)}
      >
        <div className="accordion-title-group">
          {Icon && <Icon size={18} className="accordion-icon" />}
          <div>
            <h4 className="accordion-title">{title}</h4>
            {subtitle && <p className="accordion-subtitle">{subtitle}</p>}
          </div>
        </div>
        {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>

      {open && (
        <div className="accordion-body-content">
          {children}
        </div>
      )}
    </div>
  );
}
