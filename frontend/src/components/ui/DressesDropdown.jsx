import React, { useState, useRef, useEffect } from 'react';
import { Check, Plus, ChevronDown, ChevronUp, X, Shirt, Loader2 } from 'lucide-react';

/**
 * DressesDropdown component - 3 column dropdown layout for selecting dresses/garments.
 * Designed to replace simple pill lists with a modern, high-end multi-select dropdown UI.
 */
export default function DressesDropdown({
  title = "Dresses in this Order",
  subtitle = "Pick every garment being stitched. Each one opens its own design parts below.",
  isRequired = false,
  garmentTemplates = [],
  garmentJobs = [],
  addingGarmentKey = null,
  garmentTemplatesError = null,
  loadGarmentTemplates = null,
  addGarment,
  removeGarment,
  minRequired = 0,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleToggleGarment = (e, templateKey, isChosen) => {
    e.stopPropagation();
    if (isChosen) {
      if (minRequired > 0 && garmentJobs.length <= minRequired) {
        return; // Prevent removing if minimum required limit reached
      }
      removeGarment?.(templateKey);
    } else {
      addGarment?.(templateKey);
    }
  };

  const handleRemovePill = (e, templateKey) => {
    e.stopPropagation();
    if (minRequired > 0 && garmentJobs.length <= minRequired) return;
    removeGarment?.(templateKey);
  };

  return (
    <div
      ref={dropdownRef}
      style={{
        background: 'var(--surface-color, #ffffff)',
        border: '1px solid var(--border-color, #e5e1d7)',
        borderRadius: '12px',
        padding: '16px 18px',
        marginBottom: '20px',
        textAlign: 'left',
        position: 'relative',
        boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
      }}
    >
      {/* Section Header */}
      <div style={{ marginBottom: '12px' }}>
        <label
          className="form-label"
          style={{
            fontWeight: 700,
            fontSize: '14.5px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            margin: 0,
            color: 'var(--text-primary, #1e293b)',
          }}
        >
          <Shirt size={16} style={{ color: 'var(--accent-text, #18181b)' }} />
          <span>{title}</span>
          {isRequired && <span className="required" style={{ color: '#ef4444' }}>*</span>}
        </label>
        {subtitle && (
          <div style={{ fontSize: '12.5px', color: 'var(--text-secondary, #64748b)', marginTop: '4px' }}>
            {subtitle}
          </div>
        )}
      </div>

      {/* Main Dropdown Trigger Control */}
      <div
        onClick={() => setIsOpen(!isOpen)}
        style={{
          minHeight: '46px',
          background: 'var(--background-secondary, #f8f9fa)',
          border: isOpen
            ? '1.5px solid var(--accent-color, #18181b)'
            : '1px solid var(--border-color, #e2e8f0)',
          borderRadius: '10px',
          padding: '8px 12px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          transition: 'all 0.2s ease',
          boxShadow: isOpen ? '0 0 0 3px rgba(24, 24, 27, 0.08)' : 'none',
        }}
      >
        {/* Selected Items / Pills Container */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center', flex: 1 }}>
          {garmentJobs.length === 0 ? (
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)', fontStyle: 'italic' }}>
              Select dresses to add to this order...
            </span>
          ) : (
            garmentJobs.map((job) => {
              const name = job.template?.name || job.key;
              const isOnlyOneAndMinReq = minRequired > 0 && garmentJobs.length <= minRequired;
              return (
                <span
                  key={job.key}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '20px',
                    fontSize: '12.5px',
                    fontWeight: 600,
                    background: '#18181b',
                    color: '#ffffff',
                    boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
                  }}
                >
                  <Check size={12} style={{ color: '#4ade80' }} />
                  {name}
                  {!isOnlyOneAndMinReq && (
                    <button
                      type="button"
                      onClick={(e) => handleRemovePill(e, job.key)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'rgba(255,255,255,0.7)',
                        cursor: 'pointer',
                        padding: '0 2px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        borderRadius: '50%',
                        marginLeft: '2px',
                      }}
                      title={`Remove ${name}`}
                    >
                      <X size={12} />
                    </button>
                  )}
                </span>
              );
            })
          )}
        </div>

        {/* Right Actions / Arrow Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {garmentJobs.length > 0 && (
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: '12px',
                background: 'rgba(24, 24, 27, 0.08)',
                color: 'var(--text-primary, #18181b)',
              }}
            >
              {garmentJobs.length} {garmentJobs.length === 1 ? 'Garment' : 'Garments'}
            </span>
          )}
          <div
            style={{
              color: 'var(--text-secondary, #64748b)',
              display: 'flex',
              alignItems: 'center',
              transition: 'transform 0.2s ease',
              transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            }}
          >
            <ChevronDown size={18} />
          </div>
        </div>
      </div>

      {/* Error state if templates fail to load */}
      {garmentTemplates.length === 0 && garmentTemplatesError && (
        <div style={{ fontSize: '12.5px', color: '#c0392b', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span>The garment list could not be loaded — {garmentTemplatesError}</span>
          {loadGarmentTemplates && (
            <button
              type="button"
              className="btn-secondary"
              style={{ padding: '3px 8px', fontSize: '12px' }}
              onClick={loadGarmentTemplates}
            >
              Retry
            </button>
          )}
        </div>
      )}

      {/* Dropdown Panel (3-Column Layout) */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: '6px',
            background: 'var(--surface-color, #ffffff)',
            border: '1px solid var(--border-color, #e2e8f0)',
            borderRadius: '12px',
            padding: '16px',
            boxShadow: '0 12px 30px rgba(0, 0, 0, 0.15)',
            zIndex: 999,
            animation: 'fadeIn 0.15s ease-out',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '12px',
              paddingBottom: '8px',
              borderBottom: '1px solid var(--border-color, #f1f5f9)',
            }}
          >
            <span style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-secondary, #64748b)' }}>
              Select Garments (3 Column)
            </span>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              style={{
                fontSize: '12px',
                fontWeight: 600,
                color: 'var(--accent-text, #18181b)',
                background: 'var(--background-secondary, #f1f5f9)',
                border: 'none',
                borderRadius: '6px',
                padding: '4px 10px',
                cursor: 'pointer',
              }}
            >
              Done
            </button>
          </div>

          {/* 3 Column Grid */}
          <div
            className="dresses-dropdown-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
              gap: '10px',
              maxHeight: '320px',
              overflowY: 'auto',
              paddingRight: '4px',
            }}
          >
            {garmentTemplates.map((template) => {
              const chosen = garmentJobs.some((job) => job.key === template.key);
              const isLoading = addingGarmentKey === template.key;
              const isOnlyOneAndMinReq = chosen && minRequired > 0 && garmentJobs.length <= minRequired;

              return (
                <button
                  key={template.key}
                  type="button"
                  disabled={!!addingGarmentKey || isOnlyOneAndMinReq}
                  onClick={(e) => handleToggleGarment(e, template.key, chosen)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-start',
                    gap: '8px',
                    padding: '10px 12px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: chosen ? 600 : 500,
                    textAlign: 'left',
                    width: '100%',
                    cursor: (addingGarmentKey || isOnlyOneAndMinReq) ? 'not-allowed' : 'pointer',
                    transition: 'all 0.15s ease',
                    background: chosen ? '#18181b' : 'var(--background-secondary, #f8f9fa)',
                    color: chosen ? '#ffffff' : 'var(--text-primary, #1e293b)',
                    border: chosen ? '1px solid #18181b' : '1px solid var(--border-color, #e2e8f0)',
                    boxShadow: chosen ? '0 2px 6px rgba(0,0,0,0.12)' : 'none',
                    opacity: (addingGarmentKey && !isLoading) ? 0.6 : 1,
                  }}
                  onMouseEnter={(e) => {
                    if (!chosen && !addingGarmentKey) {
                      e.currentTarget.style.background = '#f1f5f9';
                      e.currentTarget.style.borderColor = '#cbd5e1';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!chosen && !addingGarmentKey) {
                      e.currentTarget.style.background = 'var(--background-secondary, #f8f9fa)';
                      e.currentTarget.style.borderColor = 'var(--border-color, #e2e8f0)';
                    }
                  }}
                >
                  {isLoading ? (
                    <span
                      className="spin"
                      style={{
                        width: '14px',
                        height: '14px',
                        border: '2px solid currentColor',
                        borderTopColor: 'transparent',
                        borderRadius: '50%',
                        display: 'inline-block',
                        flexShrink: 0,
                      }}
                    />
                  ) : chosen ? (
                    <div
                      style={{
                        width: '18px',
                        height: '18px',
                        borderRadius: '50%',
                        background: '#ffffff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                      }}
                    >
                      <Check size={12} style={{ color: '#18181b', strokeWidth: 3 }} />
                    </div>
                  ) : (
                    <div
                      style={{
                        width: '18px',
                        height: '18px',
                        borderRadius: '50%',
                        border: '1.5px solid #cbd5e1',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                      }}
                    >
                      <Plus size={12} style={{ color: '#64748b' }} />
                    </div>
                  )}

                  <span
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      flex: 1,
                    }}
                  >
                    {isLoading ? 'Loading…' : template.name}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Responsive Style for Mobile / Small Screens */}
      <style>{`
        @media (max-width: 640px) {
          .dresses-dropdown-grid {
            grid-template-columns: repeat(1, minmax(0, 1fr)) !important;
          }
        }
      `}</style>
    </div>
  );
}
