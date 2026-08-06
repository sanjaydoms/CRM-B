import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

export function ResponsiveCard({
  title,
  subtitle,
  statusBadge,
  primaryValue,
  secondaryDetails,
  actions,
  expandableContent,
  onClickCard
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="responsive-mobile-card" onClick={onClickCard}>
      <div className="responsive-card-header">
        <div>
          <h4 className="responsive-card-title">{title}</h4>
          {subtitle && <p className="responsive-card-subtitle">{subtitle}</p>}
        </div>
        {statusBadge && <div className="responsive-card-status">{statusBadge}</div>}
      </div>

      {(primaryValue || secondaryDetails) && (
        <div className="responsive-card-body">
          {primaryValue && <div className="responsive-card-primary">{primaryValue}</div>}
          {secondaryDetails && (
            <div className="responsive-card-details">
              {secondaryDetails.map((detail, i) => (
                <div key={i} className="detail-item">
                  <span className="detail-label">{detail.label}:</span>
                  <span className="detail-value">{detail.value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {(actions || expandableContent) && (
        <div className="responsive-card-footer" onClick={(e) => e.stopPropagation()}>
          <div className="responsive-card-actions">
            {actions}
          </div>
          {expandableContent && (
            <button
              type="button"
              className="expand-toggle-btn"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? 'Less' : 'Details'}
              {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          )}
        </div>
      )}

      {expanded && expandableContent && (
        <div className="responsive-card-expanded">
          {expandableContent}
        </div>
      )}
    </div>
  );
}
