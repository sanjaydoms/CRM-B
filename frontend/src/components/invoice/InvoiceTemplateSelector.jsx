import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { InvoiceRenderer, normalizeInvoiceData } from './InvoiceTemplates';
import { Check, Sparkles, AlertCircle, Loader2, X, Eye } from 'lucide-react';

const TEMPLATE_OPTIONS = [
  {
    id: 'classic',
    name: 'Classic Template',
    tagline: 'Traditional & Formal',
    description: 'Clean, timeless layout with structured lines and prominent boutique header.'
  },
  {
    id: 'modern',
    name: 'Modern Template',
    tagline: 'Sleek & Contemporary',
    description: 'Dark accent header banner, crisp modern typography, and colored status badges.'
  },
  {
    id: 'elegant',
    name: 'Elegant Template',
    tagline: 'Luxury & Haute Couture',
    description: 'Refined serif typography, warm golden accents, and luxury sign-off footer.'
  }
];

export const InvoiceTemplateSelector = ({ currentUser }) => {
  const isOwner = !currentUser?.role || currentUser?.role === 'Owner';
  const [selectedTemplate, setSelectedTemplate] = useState('classic');
  const [availableTemplates, setAvailableTemplates] = useState(TEMPLATE_OPTIONS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState('');
  
  // State for wide popup modal
  const [previewModalTemplate, setPreviewModalTemplate] = useState(null);

  // Sample data for rendering previews
  const previewData = normalizeInvoiceData(null, null, currentUser);

  useEffect(() => {
    if (!isOwner) return;
    let isMounted = true;
    setLoading(true);
    api.getInvoiceTemplate()
      .then((data) => {
        if (isMounted) {
          if (data?.template) setSelectedTemplate(data.template);
          if (data?.templates) {
            setAvailableTemplates(TEMPLATE_OPTIONS);
          }
          setError(null);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.error("Failed to load invoice template setting:", err);
          setError(err.message || "Failed to load template settings.");
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => { isMounted = false; };
  }, [isOwner]);

  const handleSelectTemplate = async (templateId) => {
    if (saving) return;
    setSaving(true);
    setError(null);
    setSuccessMsg('');

    try {
      const res = await api.updateInvoiceTemplate(templateId);
      if (res?.template) {
        setSelectedTemplate(res.template);
        setSuccessMsg(`Invoice template updated to "${TEMPLATE_OPTIONS.find(t => t.id === templateId)?.name || templateId}".`);
        setTimeout(() => setSuccessMsg(''), 4000);
        setPreviewModalTemplate(null);
      }
    } catch (err) {
      console.error("Failed to save template selection:", err);
      setError(err.message || "Failed to update invoice template.");
    } finally {
      setSaving(false);
    }
  };

  if (!isOwner) {
    return null;
  }

  return (
    <div className="card" style={{ marginTop: '24px', padding: '24px', borderRadius: '12px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <h3 style={{ fontSize: '18px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={20} style={{ color: 'var(--primary-color, #2563eb)' }} />
            Invoice Template Selection
          </h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary, #64748b)', margin: '4px 0 0 0' }}>
            Choose the default invoice style used for all new customer bills and order downloads. Click any template to preview widely.
          </p>
        </div>
        {saving && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
            <Loader2 className="spin" size={16} /> Saving choice...
          </div>
        )}
      </div>

      {error && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 16px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '13px', marginBottom: '16px' }}>
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {successMsg && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 16px', backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontSize: '13px', marginBottom: '16px' }}>
          <Check size={16} />
          <span>{successMsg}</span>
        </div>
      )}

      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <Loader2 className="spin" size={24} style={{ margin: '0 auto 8px auto' }} />
          <p style={{ margin: 0, fontSize: '13px' }}>Loading invoice template options...</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px', marginTop: '16px' }}>
          {availableTemplates.map((template) => {
            const isSelected = selectedTemplate === template.id;
            return (
              <div
                key={template.id}
                onClick={() => setPreviewModalTemplate(template)}
                style={{
                  border: isSelected ? '2px solid var(--primary-color, #2563eb)' : '1px solid var(--border-color, #e2e8f0)',
                  borderRadius: '12px',
                  padding: '16px',
                  backgroundColor: isSelected ? 'rgba(37, 99, 235, 0.03)' : 'var(--bg-card, #ffffff)',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  position: 'relative',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between'
                }}
              >
                {/* Active Badge */}
                {isSelected && (
                  <div style={{
                    position: 'absolute',
                    top: '12px',
                    right: '12px',
                    backgroundColor: 'var(--primary-color, #2563eb)',
                    color: '#ffffff',
                    fontSize: '11px',
                    fontWeight: 700,
                    padding: '2px 8px',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    zIndex: 2
                  }}>
                    <Check size={12} /> Active
                  </div>
                )}

                <div>
                  <h4 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 2px 0', color: 'var(--text-primary, #0f172a)' }}>
                    {template.name}
                  </h4>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--primary-color, #2563eb)', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'block', marginBottom: '8px' }}>
                    {template.tagline}
                  </span>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary, #64748b)', margin: '0 0 16px 0', lineHeight: 1.4 }}>
                    {template.description}
                  </p>

                  {/* Preview Container Frame */}
                  <div style={{
                    border: '1px solid #cbd5e1',
                    borderRadius: '8px',
                    overflow: 'hidden',
                    backgroundColor: '#ffffff',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.04)',
                    height: '240px',
                    position: 'relative',
                    pointerEvents: 'none',
                    userSelect: 'none'
                  }}>
                    <div style={{
                      transform: 'scale(0.38)',
                      transformOrigin: 'top left',
                      width: '260%',
                      padding: '20px'
                    }}>
                      <InvoiceRenderer template={template.id} data={previewData} />
                    </div>
                  </div>
                </div>

                {/* Selection & Preview Buttons */}
                <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ flex: 1, justifyContent: 'center', fontSize: '12px', padding: '8px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setPreviewModalTemplate(template);
                    }}
                  >
                    <Eye size={14} /> Preview
                  </button>
                  <button
                    type="button"
                    disabled={saving}
                    className={isSelected ? 'btn-primary' : 'btn-secondary'}
                    style={{
                      flex: 1,
                      justify: 'center',
                      fontSize: '12px',
                      padding: '8px 10px',
                      backgroundColor: isSelected ? 'var(--primary-color, #2563eb)' : undefined,
                      color: isSelected ? '#ffffff' : undefined
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSelectTemplate(template.id);
                    }}
                  >
                    {isSelected ? 'Active' : 'Select'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Wide Popup Modal */}
      {previewModalTemplate && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.65)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 99999,
          padding: '20px'
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            width: '100%',
            maxWidth: '860px',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
            overflow: 'hidden'
          }}>
            {/* Modal Header */}
            <div style={{
              display: 'flex',
              justify: 'space-between',
              alignItems: 'center',
              padding: '18px 24px',
              borderBottom: '1px solid #e2e8f0',
              backgroundColor: '#f8fafc'
            }}>
              <div>
                <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#0f172a', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {previewModalTemplate.name}
                  {selectedTemplate === previewModalTemplate.id && (
                    <span style={{ fontSize: '11px', fontWeight: 700, backgroundColor: '#2563eb', color: '#fff', padding: '2px 8px', borderRadius: '12px' }}>
                      Currently Selected
                    </span>
                  )}
                </h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>{previewModalTemplate.tagline}</span>
              </div>
            </div>

            {/* Modal Body - Wide Invoice Display */}
            <div style={{ padding: '32px 40px', overflowY: 'auto', flex: 1, backgroundColor: '#ffffff' }}>
              <InvoiceRenderer template={previewModalTemplate.id} data={previewData} />
            </div>

            {/* Modal Footer Controls */}
            <div style={{
              display: 'flex',
              justify: 'space-between',
              alignItems: 'center',
              padding: '16px 24px',
              borderTop: '1px solid #e2e8f0',
              backgroundColor: '#f8fafc'
            }}>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setPreviewModalTemplate(null)}
                style={{ fontSize: '13px', padding: '8px 16px' }}
              >
                Close Preview
              </button>
              <button
                type="button"
                disabled={saving || selectedTemplate === previewModalTemplate.id}
                className="btn-primary"
                style={{
                  fontSize: '13px',
                  padding: '8px 20px',
                  backgroundColor: selectedTemplate === previewModalTemplate.id ? '#166534' : '#2563eb',
                  color: '#ffffff',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
                onClick={() => handleSelectTemplate(previewModalTemplate.id)}
              >
                {saving ? (
                  <>
                    <Loader2 className="spin" size={16} /> Applying...
                  </>
                ) : selectedTemplate === previewModalTemplate.id ? (
                  <>
                    <Check size={16} /> Active Template
                  </>
                ) : (
                  <>
                    <Check size={16} /> Select & Apply Template
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
