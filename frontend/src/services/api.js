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
  if (res.status === 413) return 'That file is too large to upload.';
  if (res.status === 404) return 'That no longer exists. It may have been removed.';
  if (res.status === 403) return 'You do not have permission to do that.';
  if (res.status >= 500) return `The server could not complete that (error ${res.status}). Please try again.`;
  return `That request failed (error ${res.status}).`;
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
    // profile_photo is an ImageField that serializes OUT as a URL string and
    // is writable IN as a file. Every screen that opens an existing customer
    // spreads the API row straight into the form, so the URL came back here as
    // a string and the field rejected it -- re-ordering for any customer who
    // had a photo died on step 1 with "Failed to update customer". Stripped
    // here rather than at the three call sites, because fixing any one of them
    // leaves the other two broken. A real File still passes through untouched.
    const payload = { ...customerData };
    if (typeof payload.profile_photo === 'string') delete payload.profile_photo;

    const res = await fetch(`${BASE_URL}/customers/${customerId}/`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const first = Object.entries(detail)[0];
      throw new Error(
        first ? `${first[0]}: ${[].concat(first[1]).join(', ')}` : 'Failed to update customer');
    }
    return res.json();
  },

  // --- Appointments ---------------------------------------------------------
  // apps/scheduling has had full CRUD since it was written and the customer's
  // tracking page already renders a trial card from it, but no frontend code
  // had ever called it -- the dashboard showed two hardcoded appointments
  // instead, naming staff who may not exist in that boutique.

  async getAppointments(params = {}) {
    const url = new URL(`${BASE_URL}/scheduling/appointments/`);
    Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.append(k, v); });
    const res = await fetch(url.toString(), { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to load appointments');
    return res.json();
  },

  async createAppointment(payload) {
    const res = await fetch(`${BASE_URL}/scheduling/appointments/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    return data;
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
    // Read the body before throwing. This used to discard the response, so the
    // API's actual explanation -- "Cannot deliver order before Master Quality
    // Check is completed." -- was replaced by a generic failure the owner
    // could not act on. Matches what transitionStage already does below.
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.error || detail.detail || 'Failed to update order status');
    }
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
    // Read the body before throwing, like updateOrderStatus does. This threw a
    // fixed string, so the Master's checklist reported "Failed to update
    // order" for what was really a 403 naming the permission.
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.error || detail.detail || 'Failed to update order');
    }
    return res.json();
  },

  // The Master's production checklist has its own narrow route: a plain PATCH
  // of the order resolves to DRF's 'partial_update', which supervisors are not
  // granted -- and must not be, because that same action carries the money
  // fields.
  async saveMasterVerification(orderId, checks) {
    const res = await fetch(`${BASE_URL}/orders/${orderId}/master-verification/`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify({ master_verification: checks }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || data.detail || 'Failed to save the checklist');
    return data;
  },

  // Customer messages. There is no WhatsApp Business integration: these are
  // queued for the owner, who sends each one from their own WhatsApp by
  // following whatsapp_url, then marks it sent.
  async getQueuedCustomerMessages() {
    const res = await fetch(`${BASE_URL}/orders/customer-messages/`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch customer messages');
    return res.json();
  },

  async markMessageSent(orderId, messageId) {
    const res = await fetch(`${BASE_URL}/orders/${orderId}/mark-message-sent/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ message_id: messageId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to mark the message sent');
    }
    return res.json();
  },

  // Finished-garment photographs. Published as a set, because publishing is
  // what tells the customer their outfit is ready.
  async uploadGarmentImage(orderId, view, file) {
    const formData = new FormData();
    formData.append('view', view);
    formData.append('image', file);
    const res = await fetch(`${BASE_URL}/orders/${orderId}/garment-images/`, {
      method: 'POST',
      headers: getHeaders(true),
      body: formData,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(describeApiError(res, data));
    return data;
  },

  async deleteGarmentImage(orderId, imageId) {
    const res = await fetch(`${BASE_URL}/orders/${orderId}/garment-images/${imageId}/`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(describeApiError(res, await res.json().catch(() => ({}))));
  },

  async publishGarmentImages(orderId, published = true) {
    const res = await fetch(`${BASE_URL}/orders/${orderId}/publish-garment-images/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ published }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(describeApiError(res, data));
    return data;
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

  // The Master's note on how to make the selected design. The endpoint has a
  // dedicated Master-only permission carve-out, a model field, a slot in
  // TailorBriefSerializer and two tests -- and its URL appeared nowhere in this
  // file, so the note could never be written from the product.
  async saveProductionNotes(boardId, itemId, notes) {
    const res = await fetch(
      `${BASE_URL}/design-studio/boards/${boardId}/items/${itemId}/production-notes/`,
      {
        method: 'PATCH',
        headers: getHeaders(),
        body: JSON.stringify({ production_notes: notes }),
      });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || 'Failed to save production notes');
    return data;
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

  // getDesignDashboard and getDesignerPortfolio used to be defined again here,
  // a second time in the same object literal. The later key silently wins in
  // JS, so the earlier pair above was unreachable and any edit made to it
  // would have been discarded without a word. One definition each, above.

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

  // Owner-only, enforced server-side by DesignStudioPermission. Creates a
  // credit-only designer -- `email` is optional here and the row carries no
  // login until createDesignerLogin runs against it.
  async createDesigner(payload) {
    const res = await fetch(`${BASE_URL}/design-studio/designers/`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.name || JSON.stringify(data));
    return data;
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


// --- Inventory: catalogue, locations, recipes, plans and reports ----------
// One small helper rather than a `new URL` dance repeated per call: every one
// of these takes optional filters and drops the ones that are unset.

const inventoryUrl = (path, params = {}) => {
  const url = new URL(`${BASE_URL}/inventory/${path}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.append(key, value);
    }
  });
  return url.toString();
};

const inventoryGet = async (path, params, what) => {
  const res = await fetch(inventoryUrl(path, params), { headers: getHeaders() });
  const raw = await res.text();
  let data = null;
  try { data = raw ? JSON.parse(raw) : null; } catch { data = null; }
  if (!res.ok) throw new Error(describeApiError(res, data));
  return data;
};

const inventoryPost = async (path, body, what) => {
  const res = await fetch(inventoryUrl(path), {
    method: 'POST', headers: getHeaders(), body: JSON.stringify(body || {}),
  });
  const raw = await res.text();
  let data = null;
  try { data = raw ? JSON.parse(raw) : null; } catch { data = null; }
  if (!res.ok) throw new Error(describeApiError(res, data));
  return data;
};

Object.assign(api, {
  // Catalogue
  getCatalogSections: () => inventoryGet('catalog/items/sections/'),
  getCatalogItems: (params) => inventoryGet('catalog/items/', params),
  stockCatalogItem: (id, payload) => inventoryPost(`catalog/items/${id}/stock/`, payload),

  // Locations and transfers
  getStockLocations: (params) => inventoryGet('locations/', params),
  getLocationStock: (id) => inventoryGet(`locations/${id}/stock/`),
  getItemLocations: (itemId) => inventoryGet(`items/${itemId}/locations/`),
  transferStock: (itemId, payload) => inventoryPost(`items/${itemId}/transfer/`, payload),

  // Recipes
  getBoms: (params) => inventoryGet('boms/', params),
  createBom: (payload) => inventoryPost('boms/', payload),
  getBomRequirements: (id, payload) => inventoryPost(`boms/${id}/requirements/`, payload),
  newBomVersion: (id) => inventoryPost(`boms/${id}/new-version/`),
  createBomLine: (payload) => inventoryPost('bom-lines/', payload),
  async deleteBomLine(id) {
    const res = await fetch(inventoryUrl(`bom-lines/${id}/`), {
      method: 'DELETE', headers: getHeaders(),
    });
    if (!res.ok && res.status !== 204) throw new Error('Could not remove the line.');
    return true;
  },

  // Order material plans
  getMaterialPlans: (params) => inventoryGet('material-plans/', params),
  planMaterials: (payload) => inventoryPost('material-plans/plan/', payload),
  getPlanAvailability: (id) => inventoryGet(`material-plans/${id}/availability/`),
  reservePlan: (id, payload) => inventoryPost(`material-plans/${id}/reserve/`, payload),
  consumePlanLine: (id, payload) => inventoryPost(`material-plans/${id}/consume/`, payload),
  releasePlanUnused: (id) => inventoryPost(`material-plans/${id}/release-unused/`),
  deductPlanPackaging: (id) => inventoryPost(`material-plans/${id}/deduct-packaging/`),
  reconcilePlan: (id) => inventoryGet(`material-plans/${id}/reconcile/`),
  closePlan: (id, payload) => inventoryPost(`material-plans/${id}/close/`, payload),
  cancelPlan: (id) => inventoryPost(`material-plans/${id}/cancel/`),

  // Customer-supplied materials
  getCustomerMaterials: (params) => inventoryGet('customer-materials/', params),
  receiveCustomerMaterial: (payload) => inventoryPost('customer-materials/', payload),
  recordCustomerMaterial: (id, action, payload) =>
    inventoryPost(`customer-materials/${id}/${action}/`, payload),

  // Reports
  getInventoryReport: (name, params) => inventoryGet(`reports/${name}/`, params),
});
