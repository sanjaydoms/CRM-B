import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { InvoiceRenderer, normalizeInvoiceData } from './InvoiceTemplates';
import { Check, Sparkles, AlertCircle, Loader2, Eye, ChevronLeft, ChevronRight } from 'lucide-react';

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
  const [currentIndex, setCurrentIndex] = useState(0);
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
          if (data?.template) {
            setSelectedTemplate(data.template);
            const idx = TEMPLATE_OPTIONS.findIndex(t => t.id === data.template);
            if (idx !== -1) setCurrentIndex(idx);
          }
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

  const handleNext = () => {
    setCurrentIndex((prev) => (prev + 1) % availableTemplates.length);
  };

  const handlePrev = () => {
    setCurrentIndex((prev) => (prev - 1 + availableTemplates.length) % availableTemplates.length);
  };

  if (!isOwner) {
    return null;
  }

  const currentTemplate = availableTemplates[currentIndex] || availableTemplates[0];
  const isSelected = selectedTemplate === currentTemplate.id;

  return (
    <div
      className="settings-card"
      style={{
        backgroundColor: 'var(--bg-primary, #ffffff)',
        border: '1px solid var(--border-color, #e2e8f0)',
        borderRadius: '16px',
        padding: '24px',
        boxShadow: '0 4px 6px -1px rgba(0,0,0,0.04), 0 2px 4px -2px rgba(0,0,0,0.02)',
        display: 'flex',
        flexDirection: 'column',
        justify: 'space-between'
      }}
    >
      <div>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ padding: '8px', borderRadius: '10px', backgroundColor: '#EEF2FF', color: '#4F46E5' }}>
              <Sparkles size={20} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)' }}>
                Invoice Template Selection
              </h2>
              <p style={{ margin: '2px 0 0 0', fontSize: '0.825rem', color: 'var(--text-secondary, #64748b)' }}>
                Choose default template layout for invoices
              </p>
            </div>
          </div>
          {saving && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)' }}>
              <Loader2 className="spin" size={14} /> Saving...
            </div>
          )}
        </div>

        {error && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 12px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '12px', marginBottom: '12px' }}>
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        {successMsg && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 12px', backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontSize: '12px', marginBottom: '12px' }}>
            <Check size={15} />
            <span>{successMsg}</span>
          </div>
        )}

        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
            <Loader2 className="spin" size={22} style={{ margin: '0 auto 8px auto' }} />
            <p style={{ margin: 0, fontSize: '12px' }}>Loading template settings...</p>
          </div>
        ) : (
          <div style={{ position: 'relative', marginTop: '12px' }}>
            {/* Single Displayed Template Card */}
            <div
              style={{
                border: isSelected ? '2px solid var(--primary-color, #2563eb)' : '1px solid var(--border-color, #e2e8f0)',
                borderRadius: '14px',
                padding: '18px',
                backgroundColor: isSelected ? 'rgba(37, 99, 235, 0.03)' : 'var(--bg-card, #ffffff)',
                position: 'relative',
                transition: 'all 0.25s ease',
                boxShadow: isSelected ? '0 4px 12px rgba(37, 99, 235, 0.08)' : 'none'
              }}
            >
              {/* Header Info */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px', paddingRight: '40px' }}>
                <div>
                  <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 2px 0', color: 'var(--text-primary, #0f172a)' }}>
                    {currentTemplate.name}
                  </h3>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--primary-color, #2563eb)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    {currentTemplate.tagline}
                  </span>
                </div>
                {isSelected ? (
                  <span style={{
                    backgroundColor: 'var(--primary-color, #2563eb)',
                    color: '#ffffff',
                    fontSize: '11px',
                    fontWeight: 700,
                    padding: '3px 10px',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}>
                    <Check size={12} /> Active Default
                  </span>
                ) : (
                  <span style={{ fontSize: '11px', color: '#64748b', backgroundColor: '#f1f5f9', padding: '3px 8px', borderRadius: '8px', fontWeight: 600 }}>
                    {currentIndex + 1} of {availableTemplates.length}
                  </span>
                )}
              </div>

              <p style={{ fontSize: '12px', color: 'var(--text-secondary, #64748b)', margin: '0 0 12px 0', lineHeight: 1.4 }}>
                {currentTemplate.description}
              </p>

              {/* Scaled Invoice Frame */}
              <div
                onClick={() => setPreviewModalTemplate(currentTemplate)}
                style={{
                  border: '1px solid #cbd5e1',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  backgroundColor: '#ffffff',
                  height: '240px',
                  position: 'relative',
                  cursor: 'pointer',
                  boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.03)'
                }}
              >
                <div style={{
                  transform: 'scale(0.35)',
                  transformOrigin: 'top left',
                  width: '280%',
                  padding: '16px',
                  pointerEvents: 'none',
                  userSelect: 'none'
                }}>
                  <InvoiceRenderer template={currentTemplate.id} data={previewData} />
                </div>
                <div style={{
                  position: 'absolute',
                  bottom: '8px',
                  right: '8px',
                  backgroundColor: 'rgba(15, 23, 42, 0.75)',
                  color: '#ffffff',
                  fontSize: '11px',
                  padding: '4px 10px',
                  borderRadius: '6px',
                  backdropFilter: 'blur(2px)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  pointerEvents: 'none'
                }}>
                  <Eye size={12} /> Click to Zoom Wide
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ marginTop: '16px', display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  disabled={saving}
                  className={isSelected ? 'btn-primary' : 'btn-secondary'}
                  style={{
                    flex: 1,
                    justifyContent: 'center',
                    fontSize: '13px',
                    padding: '8px 14px',
                    borderRadius: '8px',
                    backgroundColor: isSelected ? 'var(--primary-color, #2563eb)' : undefined,
                    color: isSelected ? '#ffffff' : undefined,
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}
                  onClick={() => handleSelectTemplate(currentTemplate.id)}
                >
                  {saving ? (
                    <>
                      <Loader2 className="spin" size={14} /> Saving...
                    </>
                  ) : isSelected ? (
                    <>
                      <Check size={14} /> Active Template
                    </>
                  ) : (
                    'Select Template'
                  )}
                </button>

                <button
                  type="button"
                  className="btn-secondary"
                  style={{ fontSize: '13px', padding: '8px 14px', display: 'flex', alignItems: 'center', gap: '6px', borderRadius: '8px' }}
                  onClick={() => setPreviewModalTemplate(currentTemplate)}
                >
                  <Eye size={14} /> Preview Wide
                </button>
              </div>
            </div>

            {/* Right Arrow Navigation Button */}
            <button
              type="button"
              onClick={handleNext}
              style={{
                position: 'absolute',
                top: '50%',
                right: '-16px',
                transform: 'translateY(-50%)',
                width: '38px',
                height: '38px',
                borderRadius: '50%',
                backgroundColor: '#ffffff',
                border: '1px solid #cbd5e1',
                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: '#2563eb',
                zIndex: 10,
                transition: 'all 0.2s ease'
              }}
              title="View Next Template"
            >
              <ChevronRight size={22} />
            </button>

            {/* Left Arrow Navigation Button */}
            <button
              type="button"
              onClick={handlePrev}
              style={{
                position: 'absolute',
                top: '50%',
                left: '-16px',
                transform: 'translateY(-50%)',
                width: '38px',
                height: '38px',
                borderRadius: '50%',
                backgroundColor: '#ffffff',
                border: '1px solid #cbd5e1',
                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: '#2563eb',
                zIndex: 10,
                transition: 'all 0.2s ease'
              }}
              title="View Previous Template"
            >
              <ChevronLeft size={22} />
            </button>
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
    </div>
  );
};
