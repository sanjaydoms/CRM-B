import React from 'react';
import { fmtDate, formatMoney, formatMobile, orderGarmentNames, orderGarmentLabel } from '../../services/format';
import { resolveMediaUrl } from '../../services/media';

/**
 * Helper to safely extract logo URL from settings.
 */
const getBoutiqueLogoUrl = (boutiqueSettings) => {
  if (!boutiqueSettings) return null;
  let logo = boutiqueSettings.logo || boutiqueSettings.boutique_logo || boutiqueSettings.logo_url;
  if (typeof logo === 'object' && logo !== null) {
    logo = logo.url || logo.path || logo.src || null;
  }
  if (!logo || typeof logo !== 'string') return null;
  return resolveMediaUrl(logo);
};

/**
 * Normalizes order & boutique data for invoice rendering.
 */
export const normalizeInvoiceData = (order, boutiqueSettings, currentUser) => {
  const getOwnerName = () => {
    if (boutiqueSettings?.owner_name) return boutiqueSettings.owner_name;
    if (boutiqueSettings?.owner) return boutiqueSettings.owner;
    if (currentUser) {
      const name = `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim();
      if (name) return name;
    }
    return 'Aditi Dey';
  };

  const ownerName = getOwnerName();
  const boutiqueLogo = getBoutiqueLogoUrl(boutiqueSettings);

  if (!order) {
    return {
      orderId: '12345',
      orderDate: new Date().toISOString(),
      customerName: 'Imani Olowe',
      customerAddress: '63 Ivy Road, Hawkville, GA, USA 31036',
      customerMobile: '123-456-7890',
      customerEmail: 'imani.olowe@example.com',
      customerType: 'Custom Tailoring',
      boutiqueName: boutiqueSettings?.name || 'Aditi Boutique',
      boutiqueAddress: boutiqueSettings?.address || 'Hyderabad',
      boutiquePhone: boutiqueSettings?.phone || '7656789876',
      boutiqueEmail: boutiqueSettings?.email || 'aditi@gmail.com',
      boutiqueLogo: boutiqueLogo,
      ownerName: ownerName,
      tailorName: 'Rajesh Kumar',
      estimatedDelivery: new Date(Date.now() + 7 * 86400000).toISOString(),
      garmentLabel: 'Eggshell Camisole Top & Cuban Collar Shirt',
      garmentNamesCount: 2,
      fabricPrice: 1500,
      occasion: 'Bespoke Collection',
      necklineStyle: 'Cuban Collar',
      sleeveStyle: 'Short Sleeve',
      backStyle: 'Standard Tailored',
      jobs: [
        { id: 1, template_name: 'Eggshell Camisole Top', qty: 1, unit_price: 123, total: 123 },
        { id: 2, template_name: 'Cuban Collar Shirt', qty: 2, unit_price: 127, total: 254 },
        { id: 3, template_name: 'Floral Cotton Dress', qty: 1, unit_price: 123, total: 123 }
      ],
      packagingHandling: 0,
      discount: 0,
      subtotal: 500,
      taxes: 0,
      totalAmount: 500,
      amountPaid: 500,
      balanceDue: 0,
      paymentStatus: 'Paid',
      invoiceTemplate: 'classic'
    };
  }

  const jobs = order.garment_jobs || [];
  const jobTotal = (job) =>
    ['base_price', 'fabric_price', 'embroidery_price', 'customization_price', 'tailoring_charges']
      .reduce((sum, key) => sum + parseFloat(job[key] || 0), 0);
  const pricedJobs = jobs.filter(j => jobTotal(j) > 0);

  const totalAmount = Number(order.total_amount || 0);
  const taxes = Number(order.taxes || 0);
  const subtotal = totalAmount - taxes;
  const amountPaid = Number(order.amount_paid || 0);
  const balanceDue = Math.max(0, totalAmount - amountPaid);

  return {
    orderId: order.order_id || '—',
    orderDate: order.order_date || new Date().toISOString(),
    customerName: order.customer_name || 'Valued Customer',
    customerAddress: order.delivery_address || order.customer_address || '',
    customerMobile: order.customer_mobile || '',
    customerEmail: order.customer_email || '',
    customerType: order.customer_type || 'Custom',
    boutiqueName: boutiqueSettings?.name || 'SCALEEZY',
    boutiqueAddress: boutiqueSettings?.address || '',
    boutiquePhone: boutiqueSettings?.phone || '',
    boutiqueEmail: boutiqueSettings?.email || '',
    boutiqueLogo: boutiqueLogo,
    ownerName: ownerName,
    tailorName: order.tailor_name || '',
    estimatedDelivery: order.estimated_delivery || '',
    garmentLabel: orderGarmentLabel(order),
    garmentNamesCount: orderGarmentNames(order).length,
    fabricPrice: Number(order.fabric_price || 0),
    occasion: order.customer_occasion || '',
    necklineStyle: order.customer_neckline_style || '',
    sleeveStyle: order.customer_sleeve_style || '',
    backStyle: order.customer_back_style || '',
    jobs: pricedJobs,
    jobTotal,
    packagingHandling: Number(order.packaging_handling || 0),
    discount: Number(order.discount || 0),
    subtotal,
    taxes,
    totalAmount,
    amountPaid,
    balanceDue,
    paymentStatus: order.payment_status || 'Pending',
    invoiceTemplate: order.invoice_template || boutiqueSettings?.invoice_template || 'classic'
  };
};

/**
 * Template 1: Reference Design 1 - Classic Monochrome Luxury
 */
export const ClassicInvoiceTemplate = ({ data }) => {
  return (
    <div className="invoice-template classic-template" style={{
      backgroundColor: '#f9f8f6',
      color: '#1c1917',
      fontSize: '13px',
      lineHeight: 1.6,
      padding: '40px 36px',
      fontFamily: "Georgia, 'Playfair Display', serif",
      borderRadius: '8px',
      boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '40px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {data.boutiqueLogo && (
            <img
              src={data.boutiqueLogo}
              alt="Boutique Logo"
              style={{ maxHeight: '60px', maxWidth: '180px', objectFit: 'contain' }}
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          )}
          <div>
            <h2 style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'serif', color: '#1c1917', margin: 0, lineHeight: 1.2 }}>
              {data.boutiqueName}
            </h2>
            {data.ownerName && (
              <span style={{ fontSize: '11px', color: '#52525b', display: 'block', marginTop: '2px', fontFamily: 'sans-serif' }}>
                Owner: {data.ownerName}
              </span>
            )}
          </div>
        </div>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 400, letterSpacing: '4px', color: '#000000', margin: 0, textTransform: 'uppercase', fontFamily: "'Playfair Display', Didot, Georgia, serif" }}>
            INVOICE
          </h1>
        </div>
      </div>

      {/* Billed To & Metadata */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '40px', fontFamily: 'sans-serif' }}>
        <div>
          <span style={{ fontSize: '11px', fontWeight: 800, color: '#1c1917', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'block', marginBottom: '6px' }}>
            BILLED TO:
          </span>
          <span style={{ fontSize: '14px', fontWeight: 600, color: '#27272a', display: 'block' }}>{data.customerName}</span>
          {data.customerMobile && <span style={{ display: 'block', color: '#52525b', fontSize: '13px' }}>{formatMobile(data.customerMobile)}</span>}
          {data.customerAddress && <span style={{ display: 'block', color: '#52525b', fontSize: '13px', maxWidth: '280px', marginTop: '2px' }}>{data.customerAddress}</span>}
        </div>
        <div style={{ textAlign: 'right', fontSize: '13px', color: '#27272a' }}>
          <div>Invoice No. <strong>{data.orderId}</strong></div>
          <div style={{ color: '#52525b', marginTop: '4px' }}>{fmtDate(data.orderDate)}</div>
        </div>
      </div>

      {/* Item Table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '32px', fontFamily: 'sans-serif' }}>
        <thead>
          <tr style={{ borderTop: '1px solid #27272a', borderBottom: '1px solid #27272a', fontSize: '11px', fontWeight: 700, color: '#1c1917' }}>
            <th style={{ padding: '12px 8px', textAlign: 'left' }}>Item</th>
            <th style={{ padding: '12px 8px', textAlign: 'center', width: '80px' }}>Quantity</th>
            <th style={{ padding: '12px 8px', textAlign: 'right', width: '100px' }}>Unit Price</th>
            <th style={{ padding: '12px 8px', textAlign: 'right', width: '110px' }}>Total</th>
          </tr>
        </thead>
        <tbody style={{ fontSize: '13px', color: '#27272a' }}>
          {!data.jobs || data.jobs.length === 0 ? (
            <tr style={{ borderBottom: '1px solid #e4e4e7' }}>
              <td style={{ padding: '14px 8px' }}>{data.garmentLabel}</td>
              <td style={{ padding: '14px 8px', textAlign: 'center' }}>1</td>
              <td style={{ padding: '14px 8px', textAlign: 'right' }}>{formatMoney(data.subtotal)}</td>
              <td style={{ padding: '14px 8px', textAlign: 'right', fontWeight: 600 }}>{formatMoney(data.subtotal)}</td>
            </tr>
          ) : (
            data.jobs.map((job, idx) => {
              const qty = job.qty || 1;
              const unitPrice = job.unit_price || (data.jobTotal ? data.jobTotal(job) : job.total || 0);
              const rowTotal = data.jobTotal ? data.jobTotal(job) : (job.total || unitPrice * qty);
              return (
                <tr key={idx} style={{ borderBottom: '1px solid #e4e4e7' }}>
                  <td style={{ padding: '14px 8px' }}>{job.template_name || 'Garment Item'}</td>
                  <td style={{ padding: '14px 8px', textAlign: 'center' }}>{qty}</td>
                  <td style={{ padding: '14px 8px', textAlign: 'right' }}>{formatMoney(unitPrice)}</td>
                  <td style={{ padding: '14px 8px', textAlign: 'right', fontWeight: 600 }}>{formatMoney(rowTotal)}</td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>

      {/* Subtotal & Total Block */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '48px', fontFamily: 'sans-serif' }}>
        <div style={{ width: '220px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: '13px', fontWeight: 700, color: '#1c1917' }}>
            <span>Subtotal</span>
            <span>{formatMoney(data.subtotal)}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: '13px', fontWeight: 700, color: '#1c1917' }}>
            <span>Tax ({data.taxes > 0 ? '5%' : '0%'})</span>
            <span>{formatMoney(data.taxes)}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 0 6px 0', borderTop: '1px solid #1c1917', fontSize: '20px', fontWeight: 800, color: '#000000', marginTop: '4px' }}>
            <span>Total</span>
            <span>{formatMoney(data.totalAmount)}</span>
          </div>
        </div>
      </div>

      {/* Thank You Signoff */}
      <div style={{ marginBottom: '40px' }}>
        <h3 style={{ fontSize: '24px', fontWeight: 400, color: '#1c1917', margin: 0, fontFamily: "Georgia, 'Playfair Display', serif" }}>
          Thank you!
        </h3>
      </div>

      {/* Footer */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderTop: '1px solid #e4e4e7', paddingTop: '20px', fontSize: '11px', color: '#52525b', fontFamily: 'sans-serif' }}>
        <div>
          <span style={{ fontWeight: 800, color: '#1c1917', textTransform: 'uppercase', display: 'block', marginBottom: '4px', letterSpacing: '0.5px' }}>
            PAYMENT INFORMATION
          </span>
          <div style={{ color: '#3f3f46', lineHeight: 1.5 }}>
            <div>Payment Status: <strong>{data.paymentStatus}</strong></div>
            {data.ownerName && <div>Boutique Owner: <strong>{data.ownerName}</strong></div>}
            {data.balanceDue > 0 && <div>Balance Owed: {formatMoney(data.balanceDue)}</div>}
          </div>
        </div>
        <div style={{ textAlign: 'right', lineHeight: 1.4 }}>
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#1c1917', display: 'block', fontFamily: "Georgia, serif" }}>
            {data.boutiqueName}
          </span>
          {data.ownerName && <span style={{ display: 'block', color: '#3f3f46', fontWeight: 600 }}>Owner: {data.ownerName}</span>}
          {data.boutiqueAddress && <span style={{ display: 'block' }}>{data.boutiqueAddress}</span>}
          {data.boutiquePhone && <span style={{ display: 'block' }}>📞 {formatMobile(data.boutiquePhone)}</span>}
          {data.boutiqueEmail && <span style={{ display: 'block' }}>✉️ {data.boutiqueEmail}</span>}
        </div>
      </div>
    </div>
  );
};

/**
 * Template 2: Reference Design 2 - Soft Blush Pink Beauty Aesthetic
 */
export const ModernInvoiceTemplate = ({ data }) => {
  return (
    <div className="invoice-template modern-template" style={{
      backgroundColor: '#ffffff',
      color: '#334155',
      fontSize: '13px',
      lineHeight: 1.5,
      padding: '36px',
      borderRadius: '12px',
      position: 'relative',
      overflow: 'hidden',
      fontFamily: "'Inter', system-ui, sans-serif",
      boxShadow: '0 2px 8px rgba(0,0,0,0.06)'
    }}>
      {/* Top Left Soft Rose Pill Decor */}
      <div style={{ position: 'absolute', top: '24px', left: '24px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ width: '64px', height: '12px', backgroundColor: '#fbcfe8', borderRadius: '10px' }}></div>
        <div style={{ width: '64px', height: '12px', backgroundColor: '#fbcfe8', borderRadius: '10px' }}></div>
        <div style={{ width: '64px', height: '12px', backgroundColor: '#fbcfe8', borderRadius: '10px' }}></div>
      </div>

      {/* Header Info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginTop: '40px', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 800, color: '#1e293b', margin: '0 0 16px 0', letterSpacing: '-0.5px' }}>
            Invoice
          </h1>
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 4px 0' }}>{data.customerName}</h3>
            <span style={{ display: 'block', fontSize: '11px', color: '#64748b' }}>Date: {fmtDate(data.orderDate)}</span>
            <span style={{ display: 'block', fontSize: '11px', color: '#64748b' }}>Invoice Nº: {data.orderId}</span>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          {data.boutiqueLogo && (
            <img
              src={data.boutiqueLogo}
              alt="Boutique Logo"
              style={{ maxHeight: '56px', maxWidth: '180px', objectFit: 'contain', marginBottom: '6px' }}
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          )}
          <span style={{ fontSize: '16px', fontWeight: 700, color: '#881337', display: 'block' }}>{data.boutiqueName}</span>
          {data.ownerName && <span style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#475569' }}>Owner: {data.ownerName}</span>}
          {data.boutiqueAddress && <span style={{ display: 'block', fontSize: '11px', color: '#64748b', marginTop: '2px' }}>📍 {data.boutiqueAddress}</span>}
          {data.boutiquePhone && <span style={{ display: 'block', fontSize: '11px', color: '#64748b' }}>📞 {formatMobile(data.boutiquePhone)}</span>}
          {data.boutiqueEmail && <span style={{ display: 'block', fontSize: '11px', color: '#64748b' }}>✉️ {data.boutiqueEmail}</span>}
        </div>
      </div>

      {/* Table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '40px' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #cbd5e1', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '1px', color: '#475569' }}>
            <th style={{ padding: '10px 4px', textAlign: 'left', fontWeight: 700 }}>DESCRIPTION</th>
            <th style={{ padding: '10px 4px', textAlign: 'center', width: '90px', fontWeight: 700 }}>QTY</th>
            <th style={{ padding: '10px 4px', textAlign: 'right', width: '120px', fontWeight: 700 }}>SUBTOTAL</th>
          </tr>
        </thead>
        <tbody style={{ fontSize: '13px', color: '#1e293b' }}>
          {!data.jobs || data.jobs.length === 0 ? (
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: '14px 4px', fontWeight: 600 }}>{data.garmentLabel}</td>
              <td style={{ padding: '14px 4px', textAlign: 'center', color: '#64748b' }}>1</td>
              <td style={{ padding: '14px 4px', textAlign: 'right', fontWeight: 700 }}>{formatMoney(data.subtotal)}</td>
            </tr>
          ) : (
            data.jobs.map((job, idx) => {
              const qty = job.qty || 1;
              const rowTotal = data.jobTotal ? data.jobTotal(job) : (job.total || 0);
              return (
                <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '14px 4px', fontWeight: 600 }}>{job.template_name || 'Garment Item'}</td>
                  <td style={{ padding: '14px 4px', textAlign: 'center', color: '#64748b' }}>{qty}</td>
                  <td style={{ padding: '14px 4px', textAlign: 'right', fontWeight: 700 }}>{formatMoney(rowTotal)}</td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>

      {/* Payment & Total Section */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderTop: '1px solid #cbd5e1', paddingTop: '16px', marginBottom: '40px' }}>
        <div>
          <span style={{ fontSize: '10px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '1px', display: 'block', marginBottom: '4px' }}>
            BOUTIQUE &amp; PAYMENT DETAILS
          </span>
          <span style={{ fontSize: '12px', color: '#64748b', display: 'block' }}>Status: <strong style={{ color: '#0f172a' }}>{data.paymentStatus}</strong></span>
          <span style={{ fontSize: '12px', color: '#64748b', display: 'block' }}>Owner: <strong style={{ color: '#0f172a' }}>{data.ownerName}</strong></span>
          {data.boutiquePhone && <span style={{ fontSize: '12px', color: '#64748b', display: 'block' }}>Contact: {formatMobile(data.boutiquePhone)}</span>}
        </div>
        <div style={{ textAlign: 'right' }}>
          <span style={{ fontSize: '10px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '1px', display: 'block', marginBottom: '2px' }}>
            TOTAL
          </span>
          <span style={{ fontSize: '28px', fontWeight: 800, color: '#be185d', lineHeight: 1 }}>
            {formatMoney(data.totalAmount)}
          </span>
        </div>
      </div>

      {/* Bottom Soft Rose Banner Decor */}
      <div style={{ backgroundColor: '#fecdd3', height: '24px', borderRadius: '12px', marginTop: '20px' }}></div>
    </div>
  );
};

/**
 * Template 3: Reference Design 3 - Earthy Warm Beige Couture with Cursive Script
 */
export const ElegantInvoiceTemplate = ({ data }) => {
  return (
    <div className="invoice-template elegant-template" style={{
      backgroundColor: '#ffffff',
      color: '#27272a',
      fontSize: '13px',
      lineHeight: 1.6,
      padding: '40px 36px',
      borderRadius: '12px',
      fontFamily: "'Inter', sans-serif",
      boxShadow: '0 2px 10px rgba(0,0,0,0.06)'
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div style={{ position: 'relative' }}>
          <div style={{
            position: 'absolute',
            left: '-10px',
            top: '8px',
            width: '180px',
            height: '36px',
            backgroundColor: '#f5ebe0',
            borderRadius: '4px',
            zIndex: 0
          }}></div>
          <h1 style={{
            position: 'relative',
            zIndex: 1,
            fontFamily: "'Dancing Script', 'Brush Script MT', 'Caveat', cursive",
            fontSize: '44px',
            fontWeight: 700,
            color: '#1c1917',
            margin: 0,
            lineHeight: 1
          }}>
            Invoice
          </h1>
        </div>
        <div style={{ textAlign: 'right' }}>
          {data.boutiqueLogo && (
            <img
              src={data.boutiqueLogo}
              alt="Boutique Logo"
              style={{ maxHeight: '60px', maxWidth: '180px', objectFit: 'contain', marginBottom: '4px', marginLeft: 'auto' }}
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          )}
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#574c43', display: 'block', marginTop: '4px' }}>{data.boutiqueName}</span>
          {data.ownerName && <span style={{ fontSize: '11px', color: '#71717a', display: 'block' }}>Owner: {data.ownerName}</span>}
        </div>
      </div>

      {/* Invoice To & Metadata */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '28px' }}>
        <div>
          <span style={{ fontSize: '12px', color: '#574c43', display: 'block', marginBottom: '2px' }}>Invoice to:</span>
          <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#1c1917', margin: '0 0 4px 0', textTransform: 'uppercase' }}>
            {data.customerName}
          </h3>
          {data.customerAddress && <span style={{ display: 'block', fontSize: '12px', color: '#71717a' }}>Address: {data.customerAddress}</span>}
          {data.customerEmail && <span style={{ display: 'block', fontSize: '12px', color: '#71717a' }}>{data.customerEmail}</span>}
          {data.customerMobile && <span style={{ display: 'block', fontSize: '12px', color: '#71717a' }}>Phone number: {formatMobile(data.customerMobile)}</span>}
        </div>
        <div style={{ textAlign: 'right', fontSize: '13px' }}>
          <div style={{ fontWeight: 600, color: '#1c1917' }}>Invoice No:</div>
          <div style={{ color: '#71717a', marginBottom: '8px' }}>#{data.orderId}</div>
          <div style={{ fontWeight: 600, color: '#1c1917' }}>Date Issued:</div>
          <div style={{ color: '#71717a' }}>{fmtDate(data.orderDate)}</div>
        </div>
      </div>

      {/* Shaded Beige Table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '24px' }}>
        <thead>
          <tr style={{ backgroundColor: '#c4b5a5', color: '#ffffff', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '1px' }}>
            <th style={{ padding: '10px 8px', textAlign: 'center', width: '40px' }}>NO</th>
            <th style={{ padding: '10px 8px', textAlign: 'left' }}>DESCRIPTION</th>
            <th style={{ padding: '10px 8px', textAlign: 'center', width: '60px' }}>QTY</th>
            <th style={{ padding: '10px 8px', textAlign: 'right', width: '90px' }}>PRICE</th>
            <th style={{ padding: '10px 8px', textAlign: 'right', width: '100px' }}>SUBTOTAL</th>
          </tr>
        </thead>
        <tbody style={{ fontSize: '12px', color: '#27272a' }}>
          {!data.jobs || data.jobs.length === 0 ? (
            <tr style={{ backgroundColor: '#ffffff', borderBottom: '1px solid #f4f4f5' }}>
              <td style={{ padding: '12px 8px', textAlign: 'center' }}>1</td>
              <td style={{ padding: '12px 8px', fontWeight: 500 }}>{data.garmentLabel}</td>
              <td style={{ padding: '12px 8px', textAlign: 'center' }}>1</td>
              <td style={{ padding: '12px 8px', textAlign: 'right' }}>{formatMoney(data.subtotal)}</td>
              <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600 }}>{formatMoney(data.subtotal)}</td>
            </tr>
          ) : (
            data.jobs.map((job, idx) => {
              const qty = job.qty || 1;
              const unitPrice = job.unit_price || (data.jobTotal ? data.jobTotal(job) : job.total || 0);
              const rowTotal = data.jobTotal ? data.jobTotal(job) : (job.total || unitPrice * qty);
              const bgColor = idx % 2 === 0 ? '#ffffff' : '#f5ebe0';
              return (
                <tr key={idx} style={{ backgroundColor: bgColor, borderBottom: '1px solid #e4e4e7' }}>
                  <td style={{ padding: '12px 8px', textAlign: 'center' }}>{idx + 1}</td>
                  <td style={{ padding: '12px 8px', fontWeight: 500 }}>{job.template_name || 'Garment Item'}</td>
                  <td style={{ padding: '12px 8px', textAlign: 'center' }}>{qty}</td>
                  <td style={{ padding: '12px 8px', textAlign: 'right' }}>{formatMoney(unitPrice)}</td>
                  <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600 }}>{formatMoney(rowTotal)}</td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>

      {/* Shaded Right Block Summary */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '40px' }}>
        <div style={{ maxWidth: '280px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#1c1917', display: 'block', marginBottom: '4px' }}>
            ATELIER DETAILS
          </span>
          <div style={{ fontSize: '11px', color: '#71717a', lineHeight: 1.5 }}>
            <div style={{ fontWeight: 700, color: '#1c1917' }}>{data.boutiqueName}</div>
            {data.ownerName && <div>Boutique Owner: {data.ownerName}</div>}
            {data.boutiqueAddress && <div>Address: {data.boutiqueAddress}</div>}
            {data.boutiquePhone && <div>Phone: {formatMobile(data.boutiquePhone)}</div>}
            {data.boutiqueEmail && <div>Email: {data.boutiqueEmail}</div>}
            <div>Payment Status: <strong>{data.paymentStatus}</strong></div>
          </div>
        </div>

        <div style={{ width: '230px' }}>
          <div style={{ backgroundColor: '#e8ddd3', padding: '8px 12px', display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight: 700, color: '#574c43', marginBottom: '2px' }}>
            <span>SUB TOTAL</span>
            <span>{formatMoney(data.subtotal)}</span>
          </div>
          <div style={{ backgroundColor: '#f5ebe0', padding: '8px 12px', display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight: 700, color: '#574c43', marginBottom: '2px' }}>
            <span>TAX</span>
            <span>{formatMoney(data.taxes)}</span>
          </div>
          {data.discount > 0 && (
            <div style={{ backgroundColor: '#f5ebe0', padding: '8px 12px', display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight: 700, color: '#574c43', marginBottom: '2px' }}>
              <span>DISCOUNT</span>
              <span>−{formatMoney(data.discount)}</span>
            </div>
          )}
          <div style={{ backgroundColor: '#c4b5a5', padding: '10px 12px', display: 'flex', justifyContent: 'space-between', fontSize: '13px', fontWeight: 800, color: '#ffffff', marginTop: '4px' }}>
            <span>TOTAL</span>
            <span>{formatMoney(data.totalAmount)}</span>
          </div>
        </div>
      </div>

      {/* Cursive Thank You Sign-off */}
      <div style={{ position: 'relative', marginTop: '20px' }}>
        <div style={{
          position: 'absolute',
          left: '0',
          bottom: '4px',
          width: '200px',
          height: '32px',
          backgroundColor: '#f5ebe0',
          borderRadius: '4px',
          zIndex: 0
        }}></div>
        <h2 style={{
          position: 'relative',
          zIndex: 1,
          fontFamily: "'Dancing Script', 'Brush Script MT', 'Caveat', cursive",
          fontSize: '40px',
          fontWeight: 700,
          color: '#1c1917',
          margin: 0,
          lineHeight: 1
        }}>
          Thank you
        </h2>
      </div>
    </div>
  );
};

/**
 * InvoiceRenderer selects the appropriate template based on code.
 */
export const InvoiceRenderer = ({ template = 'classic', data }) => {
  const code = (template || 'classic').toLowerCase();
  switch (code) {
    case 'modern':
      return <ModernInvoiceTemplate data={data} />;
    case 'elegant':
      return <ElegantInvoiceTemplate data={data} />;
    case 'classic':
    default:
      return <ClassicInvoiceTemplate data={data} />;
  }
};
