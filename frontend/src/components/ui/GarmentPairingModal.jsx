import React, { useState, useEffect } from 'react';
import { Sparkles, Check, X, Shirt, ArrowRight, Layers } from 'lucide-react';

/**
 * Garment pairing dictionary mapping primary garments to recommended pair garments and prompts.
 */
export const GARMENT_PAIR_MAP = {
  saree: {
    primaryName: 'Saree',
    prompt: 'Would you like to select / customize a Blouse and Petticoat for this Saree?',
    pairKeys: ['blouse', 'petticoat'],
    pairLabels: ['Blouse', 'Petticoat'],
  },
  lehenga: {
    primaryName: 'Lehenga',
    prompt: 'Would you like to select a matching Blouse (Choli) and Dupatta?',
    pairKeys: ['blouse', 'dupatta'],
    pairLabels: ['Blouse (Choli)', 'Dupatta'],
  },
  kurti: {
    primaryName: 'Kurti',
    prompt: 'Would you like to pair this with Bottom Wear and a Dupatta?',
    pairKeys: ['bottom_wear', 'dupatta'],
    pairLabels: ['Bottom Wear', 'Dupatta'],
  },
  anarkali: {
    primaryName: 'Anarkali',
    prompt: 'Would you like to add Bottom Wear and a Dupatta?',
    pairKeys: ['bottom_wear', 'dupatta'],
    pairLabels: ['Bottom Wear', 'Dupatta'],
  },
  suit: {
    primaryName: 'Suit (Kameez)',
    prompt: 'Would you like to customize the Bottom Wear and Dupatta style?',
    pairKeys: ['bottom_wear', 'dupatta'],
    pairLabels: ['Bottom Wear', 'Dupatta'],
  },
  gown: {
    primaryName: 'Gown',
    prompt: 'Would you like to add a matching Dupatta / Cape and Bottom Wear?',
    pairKeys: ['bottom_wear', 'dupatta'],
    pairLabels: ['Bottom Wear', 'Dupatta'],
  },
  sherwani: {
    primaryName: 'Sherwani',
    prompt: 'Would you like to add matching Bottom Wear and a Stole / Dupatta?',
    pairKeys: ['bottom_wear', 'dupatta'],
    pairLabels: ['Bottom Wear', 'Stole / Dupatta'],
  },
};

/**
 * Finds the pairing configuration for a given garment key or name.
 */
export function getGarmentPairConfig(garmentKey = '', garmentName = '') {
  const normalizedKey = (garmentKey || garmentName || '').toLowerCase().replace(/[^a-z]/g, '');
  
  for (const [key, config] of Object.entries(GARMENT_PAIR_MAP)) {
    if (normalizedKey.includes(key) || key.includes(normalizedKey)) {
      return config;
    }
  }
  return null;
}

/**
 * GarmentPairingModal component - Displays cross-sell pairing prompt when a primary garment is selected.
 */
export default function GarmentPairingModal({
  isOpen,
  onClose,
  primaryGarmentKey,
  primaryGarmentName,
  garmentTemplates = [],
  garmentJobs = [],
  onAddPairedGarments,
}) {
  const [selectedPairKeys, setSelectedPairKeys] = useState([]);

  const pairConfig = getGarmentPairConfig(primaryGarmentKey, primaryGarmentName);

  // Initialize selected pair keys when modal opens
  useEffect(() => {
    if (pairConfig?.pairKeys) {
      // Pre-check pair keys that are not already in garmentJobs
      const availablePairKeys = pairConfig.pairKeys.filter(pairKey => {
        const matchingTemplate = findMatchingTemplate(pairKey, garmentTemplates);
        if (!matchingTemplate) return false;
        return !garmentJobs.some(job => job.key === matchingTemplate.key);
      });
      setSelectedPairKeys(availablePairKeys);
    } else {
      setSelectedPairKeys([]);
    }
  }, [isOpen, primaryGarmentKey, primaryGarmentName, garmentTemplates, garmentJobs]);

  if (!isOpen || !pairConfig) return null;

  // Helper to match pairKey (e.g., 'blouse') to actual template in garmentTemplates
  function findMatchingTemplate(pairKey, templates) {
    const target = pairKey.toLowerCase().replace(/[^a-z]/g, '');
    return templates.find(t => {
      const k = (t.key || '').toLowerCase().replace(/[^a-z]/g, '');
      const n = (t.name || '').toLowerCase().replace(/[^a-z]/g, '');
      return k.includes(target) || target.includes(k) || n.includes(target) || target.includes(n);
    });
  }

  const handleTogglePairKey = (pairKey) => {
    if (selectedPairKeys.includes(pairKey)) {
      setSelectedPairKeys(prev => prev.filter(k => k !== pairKey));
    } else {
      setSelectedPairKeys(prev => [...prev, pairKey]);
    }
  };

  const handleConfirmPairing = () => {
    // Map selected pair keys to real template keys
    const templatesToAdd = selectedPairKeys
      .map(pk => findMatchingTemplate(pk, garmentTemplates))
      .filter(Boolean);

    if (templatesToAdd.length > 0 && onAddPairedGarments) {
      onAddPairedGarments(templatesToAdd.map(t => t.key));
    }
    onClose();
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(4px)',
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        animation: 'fadeIn 0.2s ease-out',
      }}
    >
      <div
        style={{
          background: 'var(--surface-color, #ffffff)',
          border: '1px solid var(--border-color, #e2e8f0)',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '480px',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.2)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '18px 20px',
            borderBottom: '1px solid var(--border-color, #f1f5f9)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--background-secondary, #f8f9fa)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: '#18181b',
                color: '#ffffff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Sparkles size={16} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: 'var(--text-primary, #1e293b)' }}>
                Recommended Garment Pairing
              </h3>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary, #64748b)' }}>
                Primary: <strong style={{ color: '#18181b' }}>{primaryGarmentName || pairConfig.primaryName}</strong>
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-secondary, #64748b)',
              cursor: 'pointer',
              padding: '4px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Content */}
        <div style={{ padding: '20px' }}>
          <p
            style={{
              fontSize: '14px',
              fontWeight: 600,
              color: 'var(--text-primary, #334155)',
              margin: '0 0 16px 0',
              lineHeight: '1.4',
            }}
          >
            {pairConfig.prompt}
          </p>

          {/* If pair items available */}
          {pairConfig.pairKeys && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '20px' }}>
              {pairConfig.pairKeys.map((pairKey, idx) => {
                const label = pairConfig.pairLabels[idx] || pairKey;
                const template = findMatchingTemplate(pairKey, garmentTemplates);
                const isAlreadyAdded = template && garmentJobs.some(j => j.key === template.key);
                const isChecked = selectedPairKeys.includes(pairKey) || isAlreadyAdded;

                return (
                  <div
                    key={pairKey}
                    onClick={() => !isAlreadyAdded && handleTogglePairKey(pairKey)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '12px 14px',
                      borderRadius: '10px',
                      border: isChecked ? '1.5px solid #18181b' : '1px solid var(--border-color, #e2e8f0)',
                      background: isChecked ? 'rgba(24, 24, 27, 0.03)' : 'var(--background-secondary, #f8f9fa)',
                      cursor: isAlreadyAdded ? 'default' : 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div
                        style={{
                          width: '20px',
                          height: '20px',
                          borderRadius: '5px',
                          border: isChecked ? 'none' : '1.5px solid #cbd5e1',
                          background: isChecked ? '#18181b' : 'transparent',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        {isChecked && <Check size={14} style={{ color: '#ffffff', strokeWidth: 3 }} />}
                      </div>
                      <span style={{ fontSize: '13.5px', fontWeight: 600, color: 'var(--text-primary, #1e293b)' }}>
                        {label}
                      </span>
                    </div>

                    {isAlreadyAdded ? (
                      <span style={{ fontSize: '11.5px', fontWeight: 600, color: '#16a34a', background: '#dcfce7', padding: '2px 8px', borderRadius: '10px' }}>
                        Added
                      </span>
                    ) : (
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary, #64748b)' }}>
                        + Add Piece
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

        </div>

        {/* Modal Footer Actions */}
        <div
          style={{
            padding: '14px 20px',
            borderTop: '1px solid var(--border-color, #f1f5f9)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: '10px',
            background: 'var(--background-secondary, #f8f9fa)',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '8px 16px',
              fontSize: '13px',
              fontWeight: 600,
              borderRadius: '8px',
              border: '1px solid var(--border-color, #cbd5e1)',
              background: '#ffffff',
              color: 'var(--text-primary, #334155)',
              cursor: 'pointer',
            }}
          >
            No / Skip
          </button>

          <button
            type="button"
            onClick={handleConfirmPairing}
            style={{
              padding: '8px 18px',
              fontSize: '13px',
              fontWeight: 600,
              borderRadius: '8px',
              border: 'none',
              background: '#18181b',
              color: '#ffffff',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
            }}
          >
            <span>Yes, Pair Selected</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
