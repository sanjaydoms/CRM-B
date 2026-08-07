const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const getHeaders = (isMultipart = false) => {
  const headers = {};
  if (!isMultipart) {
    headers['Content-Type'] = 'application/json';
  }
  const token = localStorage.getItem('token');
  if (token) {
    headers['Authorization'] = `Token ${token}`;
  }
  const tenantId = localStorage.getItem('tenant_id');
  if (tenantId) {
    headers['X-Tenant-ID'] = tenantId;
  }
  return headers;
};

/**
 * Turn a failed response into a sentence worth showing someone.
 *
 * DRF returns {field: ["message"]} for a validation failure, which is worth
 * unpacking; anything else (an HTML 500 page, a proxy's 413, an empty body)
 * has no useful text in it, so the status is all there is to report.
 */
const describeApiError = (res, data) => {
  if (data && typeof data === 'object') {
    const fields = Object.entries(data)
      .map(([key, value]) => {
        const text = Array.isArray(value) ? value.join(' ') : String(value);
        return key === 'detail' || key === 'error' ? text : `${key}: ${text}`;
      })
      .filter(Boolean);
    if (fields.length) return fields.join('\n');
  }
  if (res.status === 413) return 'That photograph is too large to upload.';
  if (res.status >= 500) return `The server could not save the upload (error ${res.status}). Please try again.`;
  return `The upload failed (error ${res.status}).`;
};

export const api = {
  // Auth API
  async login(username, password) {
    const res = await fetch(`${BASE_URL}/auth/login/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to login');
    
    // Store token and tenant_id
    if (data.token) {
      localStorage.setItem('token', data.token);
    }
    if (data.tenant_id) {
      localStorage.setItem('tenant_id', data.tenant_id);
    }
    return data;
  },

  async signup(signupData) {
    const res = await fetch(`${BASE_URL}/auth/signup/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(signupData)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to sign up');
    
    if (data.token) {
      localStorage.setItem('token', data.token);
    }
    if (data.tenant_id) {
      localStorage.setItem('tenant_id', data.tenant_id);
    }
    return data;
  },

  async logout() {
    try {
      await fetch(`${BASE_URL}/auth/logout/`, {
        method: 'POST',
        headers: getHeaders()
      });
    } catch (e) {
      console.error("Logout error on server", e);
    }
    localStorage.removeItem('token');
    localStorage.removeItem('tenant_id');
  },

  async getMe() {
    const token = localStorage.getItem('token');
    if (!token) return null;
    
    const res = await fetch(`${BASE_URL}/auth/me/`, {
      headers: getHeaders()
    });
    if (!res.ok) {
      localStorage.removeItem('token');
      return null;
    }
    const data = await res.json();
    if (data.tenant_id) {
      localStorage.setItem('tenant_id', data.tenant_id);
    }
    return data;
  },

  async seedMockData() {
    const res = await fetch(`${BASE_URL}/auth/seed-data/`, {
      method: 'POST',
      headers: getHeaders()
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error || 'Failed to seed mock data');
    }
    return res.json();
  },

  // Get dashboard data
  async getDashboard() {
    const res = await fetch(`${BASE_URL}/dashboard/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch dashboard');
    return res.json();
  },

  // Get all tailors
  async getTailors() {
    const res = await fetch(`${BASE_URL}/tailors/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch tailors');
    return res.json();
  },

  // Get boutique fabrics
  async getFabrics() {
    const res = await fetch(`${BASE_URL}/fabrics/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch fabrics');
    return res.json();
  },

  // Create customer profile (Step 1)
  async createCustomer(customerData, profilePhotoFile) {
    const formData = new FormData();
    
    // Append all text fields
    Object.keys(customerData).forEach(key => {
      if (customerData[key] !== null && customerData[key] !== undefined) {
        if (typeof customerData[key] === 'object') {
          formData.append(key, JSON.stringify(customerData[key]));
        } else {
          formData.append(key, customerData[key]);
        }
      }
    });

    if (profilePhotoFile) {
      formData.append('profile_photo', profilePhotoFile);
    }

    const res = await fetch(`${BASE_URL}/customers/`, {
      method: 'POST',
      headers: getHeaders(true), // true = multipart (no Content-Type header)
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(JSON.stringify(err) || 'Failed to create customer');
    }
    return res.json();
  },

  // Update customer (e.g. measurements, or drafts)
  async updateCustomer(customerId, customerData) {
    const res = await fetch(`${BASE_URL}/customers/${customerId}/`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(customerData),
    });
    if (!res.ok) throw new Error('Failed to update customer');
    return res.json();
  },

  // Save design preferences (Step 3)
  async saveDesignPreferences(customerId, notes, imageFiles, selectedUrls = [], source = 'BOUTIQUE_CATALOG', referenceLinks = []) {
    const formData = new FormData();
    formData.append('notes', notes);
    formData.append('selected_urls', JSON.stringify(selectedUrls));
    formData.append('source', source);
    formData.append('reference_links', JSON.stringify(referenceLinks));

    imageFiles.forEach(file => {
      formData.append('images', file);
    });

    const res = await fetch(`${BASE_URL}/customers/${customerId}/design-preferences/`, {
      method: 'POST',
      headers: getHeaders(true),
      body: formData,
    });
    if (!res.ok) throw new Error('Failed to save design preferences');
    return res.json();
  },

  // Sign off one design for production. Supersedes any previously approved design.
  async approveDesign(customerId, prefId, approvedImage = null) {
    const res = await fetch(`${BASE_URL}/customers/${customerId}/design-preferences/${prefId}/approve/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(approvedImage ? { approved_image: approvedImage } : {}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to approve design');
    }
    return res.json();
  },

  // Nominate who should perform a stage. Pass tailorId null to clear it.
  async assignStage(orderId, stageKey, tailorId) {
    const res = await fetch(`${BASE_URL}/orders/${orderId}/assign-stage/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ stage_key: stageKey, tailor_id: tailorId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to assign stage');
    }
    return res.json();
  },

  // Get AI Suggestions for a customer based on style inputs
  async getAISuggestions(customerId) {
    const res = await fetch(`${BASE_URL}/customers/${customerId}/ai-suggestions/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch AI suggestions');
    return res.json();
  },

  // Get Boutique Designs for a customer based on style inputs
  async getBoutiqueDesigns(customerId) {
    const res = await fetch(`${BASE_URL}/customers/${customerId}/boutique-designs/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch boutique designs');
    return res.json();
  },

  // Save fabric selection (Step 4)
  async saveFabricSelection(customerId, fabricData, imageFiles = []) {
    const formData = new FormData();
    formData.append('is_boutique_fabric', fabricData.is_boutique_fabric);
    formData.append('fabric_name', fabricData.fabric_name);
    formData.append('fabric_price', fabricData.fabric_price);

    imageFiles.forEach(file => {
      formData.append('images', file);
    });

    const res = await fetch(`${BASE_URL}/customers/${customerId}/fabric-selections/`, {
      method: 'POST',
      headers: getHeaders(true),
      body: formData,
    });
    if (!res.ok) throw new Error('Failed to save fabric selection');
    return res.json();
  },

  // Create order (Step 5)
  async createOrder(customerId, orderData) {
    const res = await fetch(`${BASE_URL}/customers/${customerId}/create-order/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(orderData),
    });
    if (!res.ok) throw new Error('Failed to create order');
    return res.json();
  },

  // Update order status
  async updateOrderStatus(orderId, status) {
    const res = await fetch(`${BASE_URL}/orders/${orderId}/update-status/`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error('Failed to update order status');
    return res.json();
  },

  async submitCompletion(orderId, comments, imageFile) {
    const formData = new FormData();
    if (comments) formData.append('tailor_comments', comments);
    if (imageFile) formData.append('completed_garment_image', imageFile);

    const res = await fetch(`${BASE_URL}/orders/${orderId}/submit-completion/`, {
      method: 'PATCH',
      headers: getHeaders(true),
      body: formData
    });
    if (!res.ok) throw new Error('Failed to submit completion');
    return res.json();
  },

  async getBoutiqueSettings() {
    const res = await fetch(`${BASE_URL}/boutique-settings/`, {
      method: 'GET',
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to get boutique settings');
    return res.json();
  },

  async updateBoutiqueSettings(formData) {
    const res = await fetch(`${BASE_URL}/boutique-settings/`, {
      method: 'POST',
      headers: getHeaders(true),
      body: formData
    });
    if (!res.ok) throw new Error('Failed to update boutique settings');
    return res.json();
  },

  async submitStageReview(orderId, stage, comments, imageFile, completedBy = 'Boutique Staff') {
    const formData = new FormData();
    formData.append('stage', stage);
    if (comments) formData.append('comments', comments);
    if (imageFile) formData.append('image', imageFile);
    formData.append('completed_by', completedBy);

    const res = await fetch(`${BASE_URL}/orders/${orderId}/submit-stage-review/`, {
      method: 'POST',
      headers: getHeaders(true),
      body: formData
    });
    if (!res.ok) throw new Error('Failed to submit stage review');
    return res.json();
  },

  async transitionStage(orderId, stageKey, status, comments, imageFiles = [], performedById = null) {
    const formData = new FormData();
    formData.append('stage_key', stageKey);
    formData.append('status', status);
    if (comments) formData.append('comments', comments);
    if (performedById) formData.append('performed_by_id', performedById);
    
    if (imageFiles && imageFiles.length > 0) {
      imageFiles.forEach(file => {
        formData.append('images', file);
      });
    }

    const res = await fetch(`${BASE_URL}/orders/${orderId}/transition/`, {
      method: 'POST',
      headers: getHeaders(true),
      body: formData
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Failed to transition stage');
    }
    return res.json();
  },

  async updateOrder(orderId, orderData) {
    const res = await fetch(`${BASE_URL}/orders/${orderId}/`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(orderData),
    });
    if (!res.ok) throw new Error('Failed to update order');
    return res.json();
  },

  // Fabrics CRUD
  async createFabric(fabricData) {
    const res = await fetch(`${BASE_URL}/fabrics/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(fabricData),
    });
    if (!res.ok) throw new Error('Failed to create fabric');
    return res.json();
  },

  async updateFabric(id, fabricData) {
    const res = await fetch(`${BASE_URL}/fabrics/${id}/`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(fabricData),
    });
    if (!res.ok) throw new Error('Failed to update fabric');
    return res.json();
  },

  async deleteFabric(id) {
    const res = await fetch(`${BASE_URL}/fabrics/${id}/`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to delete fabric');
    return true;
  },

  // Tailors CRUD
  async createTailor(tailorData) {
    const res = await fetch(`${BASE_URL}/tailors/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(tailorData),
    });
    if (!res.ok) throw new Error('Failed to create tailor');
    return res.json();
  },

  async updateTailor(id, tailorData) {
    const res = await fetch(`${BASE_URL}/tailors/${id}/`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(tailorData),
    });
    if (!res.ok) throw new Error('Failed to update tailor');
    return res.json();
  },

  async deleteTailor(id) {
    const res = await fetch(`${BASE_URL}/tailors/${id}/`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to delete tailor');
    return true;
  },

  // Designs CRUD
  async getAllBoutiqueDesigns() {
    const res = await fetch(`${BASE_URL}/boutique-designs/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch all boutique designs');
    return res.json();
  },

  async createBoutiqueDesign(designData) {
    const res = await fetch(`${BASE_URL}/boutique-designs/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(designData),
    });
    if (!res.ok) throw new Error('Failed to create boutique design');
    return res.json();
  },

  async updateBoutiqueDesign(id, designData) {
    const res = await fetch(`${BASE_URL}/boutique-designs/${id}/`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(designData),
    });
    if (!res.ok) throw new Error('Failed to update boutique design');
    return res.json();
  },

  async deleteBoutiqueDesign(id) {
    const res = await fetch(`${BASE_URL}/boutique-designs/${id}/`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to delete boutique design');
    return true;
  },

  // Customers & Orders full directory endpoints
  async getCustomers() {
    const res = await fetch(`${BASE_URL}/customers/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch customers');
    return res.json();
  },

  // Full customer record, including nested orders and measurement history.
  // The list endpoint returns flat rows, so open a client through this.
  async getCustomer(customerId) {
    const res = await fetch(`${BASE_URL}/customers/${customerId}/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch customer');
    return res.json();
  },

  async getOrders() {
    const res = await fetch(`${BASE_URL}/orders/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch orders');
    return res.json();
  },

  // --- Inventory ---
  async getInventoryItems(params = {}) {
    const url = new URL(`${BASE_URL}/inventory/items/`);
    Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.append(k, v); });
    const res = await fetch(url.toString(), { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch inventory');
    return res.json();
  },

  async getInventorySummary() {
    const res = await fetch(`${BASE_URL}/inventory/items/summary/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch inventory summary');
    return res.json();
  },

  async getInventoryOptions() {
    const res = await fetch(`${BASE_URL}/inventory/items/options/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch inventory options');
    return res.json();
  },

  async saveInventoryItem(itemData, itemId = null) {
    const res = await fetch(
      itemId ? `${BASE_URL}/inventory/items/${itemId}/` : `${BASE_URL}/inventory/items/`,
      {
        method: itemId ? 'PATCH' : 'POST',
        headers: getHeaders(),
        body: JSON.stringify(itemData),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || JSON.stringify(err) || 'Failed to save item');
    }
    return res.json();
  },

  // Every stock change goes through one of the movement endpoints so the ledger
  // stays in step; the quantity fields themselves are read-only.
  async moveStock(itemId, movement, payload) {
    const res = await fetch(`${BASE_URL}/inventory/items/${itemId}/${movement}/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to record stock movement');
    }
    return res.json();
  },

  async getItemMovements(itemId) {
    const res = await fetch(`${BASE_URL}/inventory/items/${itemId}/movements/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch stock history');
    return res.json();
  },

  async getSuppliers() {
    const res = await fetch(`${BASE_URL}/inventory/suppliers/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch suppliers');
    return res.json();
  },

  async createSupplier(data) {
    const res = await fetch(`${BASE_URL}/inventory/suppliers/`, {
      method: 'POST', headers: getHeaders(), body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to create supplier');
    return res.json();
  },

  async getPurchaseOrders() {
    const res = await fetch(`${BASE_URL}/inventory/purchase-orders/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch purchase orders');
    return res.json();
  },

  async createPurchaseOrder(data) {
    const res = await fetch(`${BASE_URL}/inventory/purchase-orders/`, {
      method: 'POST', headers: getHeaders(), body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || JSON.stringify(err) || 'Failed to create purchase order');
    }
    return res.json();
  },

  async receivePurchaseOrder(poId, lines) {
    const res = await fetch(`${BASE_URL}/inventory/purchase-orders/${poId}/receive/`, {
      method: 'POST', headers: getHeaders(), body: JSON.stringify({ lines }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to receive goods');
    }
    return res.json();
  },

  async getNotifications(role = 'Owner', email = '') {
    const url = new URL(`${BASE_URL}/notifications/`);
    url.searchParams.append('role', role);
    if (email) url.searchParams.append('email', email);
    const res = await fetch(url.toString(), {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch notifications');
    return res.json();
  },

  async markNotificationsAsRead(role = 'Owner', email = '') {
    const url = new URL(`${BASE_URL}/notifications/mark-all-read/`);
    url.searchParams.append('role', role);
    if (email) url.searchParams.append('email', email);
    const res = await fetch(url.toString(), {
      method: 'POST',
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to mark notifications as read');
    return res.json();
  },

  // --- AI Design Studio ---------------------------------------------
  async getDesignContext(customerId, orderInput = {}) {
    const url = new URL(`${BASE_URL}/design-studio/context/`);
    url.searchParams.append('customer_id', customerId);
    Object.entries(orderInput).forEach(([key, value]) => {
      if (value) url.searchParams.append(key, value);
    });
    const res = await fetch(url.toString(), { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load design context');
    return res.json();
  },

  async discoverDesigns(payload) {
    const res = await fetch(`${BASE_URL}/design-studio/discover/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Failed to search designs');
    return res.json();
  },

  async createDesignBoard(customerId, title = '', contextSnapshot = {}, queries = []) {
    const res = await fetch(`${BASE_URL}/design-studio/boards/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        customer: customerId,
        title,
        context_snapshot: contextSnapshot,
        search_queries: queries
      })
    });
    if (!res.ok) throw new Error('Failed to create design board');
    return res.json();
  },

  async getDesignBoards(params = {}) {
    const url = new URL(`${BASE_URL}/design-studio/boards/`);
    Object.entries(params).forEach(([key, value]) => {
      if (value) url.searchParams.append(key, value);
    });
    const res = await fetch(url.toString(), { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load design boards');
    return res.json();
  },

  async addDesignToBoard(boardId, design) {
    const res = await fetch(`${BASE_URL}/design-studio/boards/${boardId}/items/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(design)
    });
    if (!res.ok) throw new Error('Failed to shortlist design');
    return res.json();
  },

  async removeDesignFromBoard(boardId, itemId) {
    const res = await fetch(`${BASE_URL}/design-studio/boards/${boardId}/items/${itemId}/`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to remove design');
    return true;
  },

  async selectBoardDesign(boardId, itemId) {
    const res = await fetch(`${BASE_URL}/design-studio/boards/${boardId}/items/${itemId}/select/`, {
      method: 'POST',
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to select design');
    return res.json();
  },

  async customiseBoardDesign(boardId, itemId, changes) {
    const res = await fetch(`${BASE_URL}/design-studio/boards/${boardId}/items/${itemId}/customise/`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(changes)
    });
    if (!res.ok) throw new Error('Failed to save customisation');
    return res.json();
  },

  async approveDesignBoard(boardId) {
    const res = await fetch(`${BASE_URL}/design-studio/boards/${boardId}/approve/`, {
      method: 'POST',
      headers: getHeaders()
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to approve design');
    return data;
  },

  // --- Design library ---------------------------------------------------

  async getDesignCategories() {
    const res = await fetch(`${BASE_URL}/design-studio/categories/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load design categories');
    return res.json();
  },

  async getDesignLibrary(params = {}) {
    const url = new URL(`${BASE_URL}/design-studio/assets/`);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) url.searchParams.append(k, v);
    });
    const res = await fetch(url.toString(), { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load the design library');
    return res.json();
  },

  async reviewDesign(id, decision, note = '') {
    const res = await fetch(`${BASE_URL}/design-studio/assets/${id}/review/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ decision, note })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(JSON.stringify(data));
    return data;
  },

  async getDesignApprovalHistory(id) {
    const res = await fetch(`${BASE_URL}/design-studio/assets/${id}/approval-history/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load approval history');
    return res.json();
  },

  async getDesignDashboard() {
    const res = await fetch(`${BASE_URL}/design-studio/dashboard/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load the design dashboard');
    return res.json();
  },

  async getDesignerPortfolio(id) {
    const res = await fetch(`${BASE_URL}/design-studio/designers/${id}/portfolio/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load the portfolio');
    return res.json();
  },

  // Owner-only: switches a credited designer on so they can sign in for
  // themselves. Idempotent server-side -- a second call against an
  // already-linked designer is refused rather than silently reissuing.
  async createDesignerLogin(id, email) {
    const res = await fetch(`${BASE_URL}/design-studio/designers/${id}/create-login/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ email })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.email || JSON.stringify(data));
    return data;
  },

  async getDesignAsset(id) {
    const res = await fetch(`${BASE_URL}/design-studio/assets/${id}/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load the design');
    return res.json();
  },

  async getDesignDashboard() {
    const res = await fetch(`${BASE_URL}/design-studio/dashboard/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load the design dashboard');
    return res.json();
  },

  async getDesignerPortfolio(id) {
    const res = await fetch(`${BASE_URL}/design-studio/designers/${id}/portfolio/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load the portfolio');
    return res.json();
  },

  async getCollections(params = {}) {
    const url = new URL(`${BASE_URL}/design-studio/collections/`);
    Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.append(k, v); });
    const res = await fetch(url.toString(), { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load collections');
    return res.json();
  },

  async createCollection(payload) {
    const res = await fetch(`${BASE_URL}/design-studio/collections/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(JSON.stringify(data));
    return data;
  },

  // Multipart: the browser posts the photographs themselves rather than the
  // boutique having to host an image somewhere and paste a URL.
  async uploadDesign(fields, imageFiles = []) {
    const form = new FormData();
    Object.entries(fields).forEach(([key, value]) => {
      if (value === '' || value === null || value === undefined) return;
      form.append(key, typeof value === 'object' ? JSON.stringify(value) : value);
    });
    imageFiles.forEach(file => form.append('images', file));

    const res = await fetch(`${BASE_URL}/design-studio/assets/`, {
      method: 'POST',
      headers: getHeaders(true),
      body: form
    });

    // Read the body as text first. res.json() on a non-JSON body rejects with
    // whatever the engine's parser says, and that message reaches the user
    // verbatim -- on WebKit it is "The string did not match the expected
    // pattern", which describes neither what failed nor what to do about it.
    // A 500 renders as an HTML page, so this is the path any server error
    // takes, not an edge case.
    const raw = await res.text();
    let data = null;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      data = null;
    }

    if (!res.ok) throw new Error(describeApiError(res, data));
    return data;
  },

  async getDesigners(params = {}) {
    const url = new URL(`${BASE_URL}/design-studio/designers/`);
    Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.append(k, v); });
    const res = await fetch(url.toString(), { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load designers');
    return res.json();
  },

  // --- Garment templates ---------------------------------------------------
  // The order form is rendered from these, so a new garment or a changed option
  // list reaches the wizard without a frontend release.

  async getGarmentTemplates() {
    const res = await fetch(`${BASE_URL}/catalog/templates/`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load garment templates');
    return res.json();
  },

  async getGarmentTemplate(key) {
    const res = await fetch(`${BASE_URL}/catalog/templates/${key}/`, { headers: getHeaders() });
    if (!res.ok) throw new Error(`Failed to load the ${key} template`);
    return res.json();
  },

  async createGarmentJob(payload) {
    const res = await fetch(`${BASE_URL}/catalog/jobs/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(JSON.stringify(data));
    return data;
  },

  async getGarmentJobs(orderId) {
    const res = await fetch(`${BASE_URL}/catalog/jobs/?order=${encodeURIComponent(orderId)}`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to load the garments on this order');
    return res.json();
  },

  async saveDesignBoardToOrder(boardId, orderId) {
    const res = await fetch(`${BASE_URL}/design-studio/boards/${boardId}/save-to-order/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ order_id: orderId })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to attach design to order');
    return data;
  }
};
