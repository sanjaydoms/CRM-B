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
  async saveDesignPreferences(customerId, notes, imageFiles, selectedUrls = []) {
    const formData = new FormData();
    formData.append('notes', notes);
    formData.append('selected_urls', JSON.stringify(selectedUrls));
    
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

  async getOrders() {
    const res = await fetch(`${BASE_URL}/orders/`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch orders');
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
  }
};
