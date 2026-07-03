import React, { useState, useEffect } from 'react';
import { 
  Users, ShoppingBag, Scissors, Search, 
  Upload, Check, ArrowRight, ArrowLeft, Heart, 
  MessageSquare, Star, Copy, ShieldCheck, Compass, BarChart2,
  FolderOpen, Sparkles, HelpCircle, X, ExternalLink,
  ChevronRight, Lock, Mail, Phone, Calendar, Landmark, 
  FileText, Bell, User, MapPin, Eye, EyeOff, Edit2, Plus, Trash2, LogOut
} from 'lucide-react';
import { api } from './services/api';

const GARMENT_PRICES = {
  'Lehenga': 32000,
  'Gown': 25000,
  'Saree': 15000,
  'Anarkali': 18000,
  'Kurti': 5000,
  'Sherwani': 35000,
  'Suit': 22000
};

const DEFAULT_CUSTOMER_DATA = {
  first_name: '',
  last_name: '',
  mobile_number: '',
  email_address: '',
  address: '',
  city_region: '',
  source: 'Walk In',
  customer_type: 'Women',
  garment_type: 'Lehenga',
  neckline_style: '',
  sleeve_style: '',
  back_style: '',
  length_preference: '',
  silhouette: '',
  embellishments: '',
  pattern_style: '',
  occasion: '',
  custom_requirements: '',
  date_of_birth: '',
  occupation: '',
  preferred_communication: 'WhatsApp',
  notes: '',
  measurements: {
    bust: '',
    waist: '',
    hips: '',
    shoulder: '',
    arm_length: '',
    neck: '',
    length: ''
  }
};

const getColorCircleStyle = (colorName) => {
  if (!colorName) return '#fbeedb';
  const name = colorName.toLowerCase();
  if (name.includes('rose') || name.includes('pink')) return '#e2a3a1';
  if (name.includes('gold')) return '#d4af37';
  if (name.includes('black') || name.includes('charcoal')) return '#2e2e2e';
  if (name.includes('blue')) return '#4169e1';
  if (name.includes('green') || name.includes('olive')) return '#556b2f';
  if (name.includes('maroon') || name.includes('red')) return '#800000';
  if (name.includes('white') || name.includes('cream')) return '#fafafa';
  return '#fbeedb';
};

const getTailorAvatarUrl = (name) => {
  if (!name) return '';
  const n = name.toLowerCase();
  if (n.includes('rohit')) return 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150';
  if (n.includes('anya')) return 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150';
  if (n.includes('rahul')) return 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150';
  if (n.includes('preeti')) return 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150';
  return 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=150';
};

const getTailorTags = (name) => {
  if (!name) return [];
  const n = name.toLowerCase();
  if (n.includes('rohit')) return ['Ethnic Wear', 'Sherwani', 'Indo-Western'];
  if (n.includes('anya')) return ['Ethnic Wear', 'Lehenga', 'Blouse'];
  if (n.includes('rahul')) return ['Gown', 'Suit', 'Formal Wear'];
  if (n.includes('preeti')) return ['Embroidery', 'Zardozi', 'Artisan'];
  return ['Custom', 'Tailoring'];
};

function App() {
  const [view, setView] = useState('landing'); // 'landing', 'login', 'signup', 'dashboard', 'order-selector', 'wizard', 'confirmed'
  const [dashboardTab, setDashboardTab] = useState('overview'); // 'overview', 'fabrics', 'tailors', 'designs'
  const [currentUser, setCurrentUser] = useState(null);
  
  // Login Form State
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);

  // Signup Wizard State
  const [signupStep, setSignupStep] = useState(1); // 1: Account, 2: Verify, 3: Profile, 4: Prefs, 5: Complete
  const [signupForm, setSignupForm] = useState({
    first_name: '',
    last_name: '',
    email_address: '',
    mobile_number: '',
    password: ''
  });
  const [otpCode, setOtpCode] = useState('');
  const [profileOccupation, setProfileOccupation] = useState('');
  const [profileComm, setProfileComm] = useState('WhatsApp');

  // Customer/Order Wizard State
  const [currentStep, setCurrentStep] = useState(1);
  const [customerId, setCustomerId] = useState(null);
  const [customerForm, setCustomerForm] = useState(DEFAULT_CUSTOMER_DATA);
  const [profilePhoto, setProfilePhoto] = useState(null);
  const [profilePhotoPreview, setProfilePhotoPreview] = useState(null);
  
  // Wizard Details State
  const [designNotes, setDesignNotes] = useState('');
  const [designFiles, setDesignFiles] = useState([]);
  const [designPreviews, setDesignPreviews] = useState([]);
  const [designSourceTab, setDesignSourceTab] = useState('references'); // 'references', 'ai', 'catalog'
  const [selectedDesignTemplates, setSelectedDesignTemplates] = useState([]);
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [boutiqueDesigns, setBoutiqueDesigns] = useState([]);
  const [designsLoading, setDesignsLoading] = useState(false);
  const [fabricTab, setFabricTab] = useState('boutique'); // 'my-fabric', 'boutique'
  const [paymentPhase, setPaymentPhase] = useState(false);
  const [paymentOption, setPaymentOption] = useState('full'); // 'full' or 'partial'
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [specialInstructions, setSpecialInstructions] = useState('');

  // Fetch dynamic AI Suggestions and Boutique Designs on entering Step 3
  useEffect(() => {
    const fetchDynamicDesigns = async () => {
      if (currentStep === 3 && customerId) {
        setDesignsLoading(true);
        try {
          const ai = await api.getAISuggestions(customerId);
          const boutique = await api.getBoutiqueDesigns(customerId);
          setAiSuggestions(ai);
          setBoutiqueDesigns(boutique);
        } catch (err) {
          console.error("Failed to load suggestions & boutique designs", err);
        } finally {
          setDesignsLoading(false);
        }
      }
    };
    fetchDynamicDesigns();
  }, [currentStep, customerId]);
  const [fabricFiles, setFabricFiles] = useState([]);
  const [fabricPreviews, setFabricPreviews] = useState([]);
  const [selectedFabric, setSelectedFabric] = useState(null);
  const [fabricFilter, setFabricFilter] = useState('All');
  const [selectedTailor, setSelectedTailor] = useState(null);
  const [quotePrices, setQuotePrices] = useState({
    base: 0,
    fabric: 0,
    embroidery: 7500,
    customization: 2500,
    tailoring: 5000,
    packaging: 500
  });
  const [showInvoiceModal, setShowInvoiceModal] = useState(false);

  // Fabrics CRUD State
  const [showFabricModal, setShowFabricModal] = useState(false);
  const [editingFabric, setEditingFabric] = useState(null);
  const [fabricForm, setFabricForm] = useState({
    name: '',
    material: '',
    color: '',
    price_per_meter: '',
    image_url: '',
    is_available: true
  });

  // Tailors CRUD State
  const [showTailorModal, setShowTailorModal] = useState(false);
  const [editingTailor, setEditingTailor] = useState(null);
  const [tailorForm, setTailorForm] = useState({
    name: '',
    specialty: '',
    rating: 5.0,
    status: 'Available'
  });

  // Designs CRUD State
  const [showDesignModal, setShowDesignModal] = useState(false);
  const [editingDesign, setEditingDesign] = useState(null);
  const [designForm, setDesignForm] = useState({
    name: '',
    garment_type: 'Lehenga',
    neckline_style: '',
    sleeve_style: '',
    image_url: '',
    is_boutique: true,
    price: 0,
    description: ''
  });

  // Sync quote prices dynamically based on Garment and Fabric selections
  useEffect(() => {
    const base = GARMENT_PRICES[customerForm.garment_type] || 15000;
    const fabric = fabricTab === 'boutique' && selectedFabric ? parseFloat(selectedFabric.price_per_meter) * 3 : 0.00;
    setQuotePrices(prev => ({
      ...prev,
      base,
      fabric
    }));
  }, [customerForm.garment_type, selectedFabric, fabricTab]);

  // Active Selected Dashboard Order for progress tracker
  const [selectedDashboardOrder, setSelectedDashboardOrder] = useState(null);
  const [expandedDna, setExpandedDna] = useState({});

  // Backend fetched collections
  const [dashboardData, setDashboardData] = useState(null);
  const [tailors, setTailors] = useState([]);
  const [fabrics, setFabrics] = useState([]);
  const [allDesigns, setAllDesigns] = useState([]);
  const [customersList, setCustomersList] = useState([]);
  const [ordersList, setOrdersList] = useState([]);
  const [confirmedOrder, setConfirmedOrder] = useState(null);

  // Existing Customer Search Modal
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [searchModalQuery, setSearchModalQuery] = useState('');
  const [allCustomers, setAllCustomers] = useState([]);

  // Search & Filters for dashboard
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  // Persisted Session check
  useEffect(() => {
    checkAuthSession();
  }, []);

  const checkAuthSession = async () => {
    try {
      const user = await api.getMe();
      if (user) {
        setCurrentUser(user);
        setView('dashboard');
        fetchDashboardAndConfig();
      }
    } catch (e) {
      console.log("No saved session");
    } finally {
      setLoading(false);
    }
  };

  const fetchDashboardAndConfig = async () => {
    setLoading(true);
    try {
      const dbData = await api.getDashboard();
      setDashboardData(dbData);
      
      const tailorList = await api.getTailors();
      setTailors(tailorList);
      
      const fabricList = await api.getFabrics();
      setFabrics(fabricList);

      const designList = await api.getAllBoutiqueDesigns();
      setAllDesigns(designList);

      const custList = await api.getCustomers();
      setCustomersList(custList);
      setAllCustomers(custList);

      const ordList = await api.getOrders();
      setOrdersList(ordList);

      // Default select first order in the dashboard tracker
      if (dbData?.recent_orders?.length > 0) {
        setSelectedDashboardOrder(dbData.recent_orders[0]);
      }
    } catch (err) {
      console.error("Error loading dashboard configs", err);
    } finally {
      setLoading(false);
    }
  };

  // Catalog Management Handlers
  const handleSaveFabric = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...fabricForm,
        price_per_meter: parseFloat(fabricForm.price_per_meter) || 0.00
      };
      if (editingFabric) {
        await api.updateFabric(editingFabric.id, payload);
      } else {
        if (!payload.image_url) {
          // Curated Unsplash fabric texture image
          payload.image_url = 'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400';
        }
        await api.createFabric(payload);
      }
      setShowFabricModal(false);
      setEditingFabric(null);
      setFabricForm({ name: '', material: '', color: '', price_per_meter: '', image_url: '', is_available: true });
      fetchDashboardAndConfig();
    } catch (err) {
      alert("Failed to save fabric: " + err.message);
    }
  };

  const handleDeleteFabric = async (id) => {
    if (window.confirm("Are you sure you want to delete this fabric?")) {
      try {
        await api.deleteFabric(id);
        fetchDashboardAndConfig();
      } catch (err) {
        alert("Failed to delete fabric: " + err.message);
      }
    }
  };

  const handleSaveTailor = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...tailorForm,
        rating: parseFloat(tailorForm.rating) || 5.0
      };
      if (editingTailor) {
        await api.updateTailor(editingTailor.id, payload);
      } else {
        await api.createTailor(payload);
      }
      setShowTailorModal(false);
      setEditingTailor(null);
      setTailorForm({ name: '', specialty: '', rating: 5.0, status: 'Available' });
      fetchDashboardAndConfig();
    } catch (err) {
      alert("Failed to save tailor: " + err.message);
    }
  };

  const handleDeleteTailor = async (id) => {
    if (window.confirm("Are you sure you want to delete this tailor?")) {
      try {
        await api.deleteTailor(id);
        fetchDashboardAndConfig();
      } catch (err) {
        alert("Failed to delete tailor: " + err.message);
      }
    }
  };

  const handleSaveDesign = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...designForm,
        price: parseFloat(designForm.price) || 0.00,
        is_boutique: designForm.is_boutique === true || designForm.is_boutique === 'true'
      };
      if (!payload.image_url) {
        // Curated apparel image
        payload.image_url = 'https://images.unsplash.com/photo-1610030469668-93535c17b6b3?w=400';
      }
      if (editingDesign) {
        await api.updateBoutiqueDesign(editingDesign.id, payload);
      } else {
        await api.createBoutiqueDesign(payload);
      }
      setShowDesignModal(false);
      setEditingDesign(null);
      setDesignForm({ name: '', garment_type: 'Lehenga', neckline_style: '', sleeve_style: '', image_url: '', is_boutique: true, price: 0, description: '' });
      fetchDashboardAndConfig();
    } catch (err) {
      alert("Failed to save design: " + err.message);
    }
  };

  const handleDeleteDesign = async (id) => {
    if (window.confirm("Are you sure you want to delete this design?")) {
      try {
        await api.deleteBoutiqueDesign(id);
        fetchDashboardAndConfig();
      } catch (err) {
        alert("Failed to delete design: " + err.message);
      }
    }
  };

  // Auth Action Handlers
  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    if (!loginEmail || !loginPassword) {
      alert("Please fill in all credentials.");
      return;
    }
    try {
      const res = await api.login(loginEmail, loginPassword);
      setCurrentUser(res.user);
      setView('dashboard');
      fetchDashboardAndConfig();
    } catch (err) {
      alert(err.message || "Invalid credentials.");
    }
  };

  const handleSignupSubmit = async (e) => {
    e.preventDefault();
    if (!signupForm.first_name || !signupForm.last_name || !signupForm.email_address || !signupForm.password) {
      alert("Please enter all required signup fields.");
      return;
    }
    setSignupStep(2); // Mock verification
  };

  const handleVerifyOTP = async () => {
    if (!otpCode) {
      alert("Please enter the verification code sent to your phone/email.");
      return;
    }
    setSignupStep(3); // Enter profile info
  };

  const handleProfileSubmit = () => {
    setSignupStep(4); // Select preferences
  };

  const handleCompleteRegistration = async () => {
    try {
      const res = await api.signup({
        first_name: signupForm.first_name,
        last_name: signupForm.last_name,
        email_address: signupForm.email_address,
        mobile_number: signupForm.mobile_number,
        password: signupForm.password,
        occupation: profileOccupation,
        preferred_communication: profileComm
      });
      setCurrentUser(res.user);
      setSignupStep(5);
      setTimeout(() => {
        setView('dashboard');
        fetchDashboardAndConfig();
      }, 1500);
    } catch (err) {
      alert(err.message || "Registration failed.");
      setSignupStep(1);
    }
  };

  const handleLogout = async () => {
    await api.logout();
    setCurrentUser(null);
    setView('landing');
  };

  // Start Order Creation Flows
  const handleStartNewCustomer = () => {
    setCustomerId(null);
    setCustomerForm(DEFAULT_CUSTOMER_DATA);
    setProfilePhoto(null);
    setProfilePhotoPreview(null);
    setDesignNotes('');
    setDesignFiles([]);
    setDesignPreviews([]);
    setFabricFiles([]);
    setFabricPreviews([]);
    setSelectedFabric(null);
    setSelectedTailor(null);
    setCurrentStep(1);
    setView('wizard');
  };

  const handleSelectExistingCustomer = async (cust) => {
    setShowSearchModal(false);
    setCustomerId(cust.id);
    setCustomerForm({
      ...DEFAULT_CUSTOMER_DATA,
      ...cust,
      measurements: cust.measurements || DEFAULT_CUSTOMER_DATA.measurements
    });
    
    // Start from the beginning (Step 1: Dress/Garment Type)
    setCurrentStep(1);
    setView('wizard');
  };

  const openExistingCustomerModal = async () => {
    setShowSearchModal(true);
    try {
      // Query customers from backend
      const res = await api.getDashboard();
      setAllCustomers(res.recent_customers || []);
    } catch (e) {
      console.error(e);
    }
  };

  // Wizard Step actions
  const handleBack = () => {
    if (currentStep === 6) {
      if (paymentPhase) {
        setPaymentPhase(false);
      } else {
        setCurrentStep(5);
      }
    } else if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    } else {
      setView('order-selector');
    }
  };

  const saveStep1 = async () => {
    if (!customerForm.first_name || !customerForm.last_name || !customerForm.mobile_number) {
      alert("Please fill in First Name, Last Name, and Mobile Number.");
      throw new Error("Validation failed");
    }
    
    try {
      if (customerId) {
        const res = await api.updateCustomer(customerId, customerForm);
        return res;
      } else {
        const res = await api.createCustomer(customerForm, profilePhoto);
        setCustomerId(res.id);
        return res;
      }
    } catch (err) {
      let errMsg = err.message;
      try {
        const parsed = JSON.parse(err.message);
        if (parsed.mobile_number) {
          errMsg = `Mobile Number: ${parsed.mobile_number.join(', ')}`;
        } else if (parsed.email_address) {
          errMsg = `Email: ${parsed.email_address.join(', ')}`;
        } else {
          errMsg = Object.keys(parsed).map(k => `${k}: ${parsed[k]}`).join('\n');
        }
      } catch (e) {
        // Use default errMsg
      }
      alert("Failed to save customer: " + errMsg);
      throw err;
    }
  };

  const saveStep2 = async () => {
    if (!customerId) return;
    const res = await api.updateCustomer(customerId, {
      measurements: customerForm.measurements
    });
    return res;
  };

  const saveStep3 = async () => {
    if (!customerId) return;
    const res = await api.saveDesignPreferences(customerId, designNotes, designFiles, selectedDesignTemplates);
    return res;
  };

  const saveStep4 = async () => {
    if (!customerId) return;
    
    let fabricPayload = {
      is_boutique_fabric: fabricTab === 'boutique',
      fabric_name: fabricTab === 'boutique' && selectedFabric ? selectedFabric.name : 'Customer Uploaded Fabric',
      fabric_price: fabricTab === 'boutique' && selectedFabric ? selectedFabric.price_per_meter * 3 : 0.00
    };

    const res = await api.saveFabricSelection(customerId, fabricPayload, fabricFiles);
    return res;
  };

  const submitOrderAndConfirm = async () => {
    if (!customerId) return;
    
    const base = parseFloat(quotePrices.base || 0);
    const fabricPrice = parseFloat(quotePrices.fabric || 0);
    const embroidery = parseFloat(quotePrices.embroidery || 0);
    const customization = parseFloat(quotePrices.customization || 0);
    const tailoring = parseFloat(quotePrices.tailoring || 0);
    const packaging = parseFloat(quotePrices.packaging || 0);

    const payload = {
      tailor_id: selectedTailor ? selectedTailor.id : null,
      base_price: base,
      fabric_price: fabricPrice,
      embroidery_price: embroidery,
      customization_price: customization,
      tailoring_charges: tailoring,
      packaging_handling: packaging,
      payment_status: paymentOption === 'full' ? 'Paid' : 'Partially Paid',
      custom_requirements: specialInstructions || customerForm.custom_requirements
    };

    try {
      const order = await api.createOrder(customerId, payload);
      setConfirmedOrder(order);
      setView('confirmed');
    } catch (err) {
      console.error(err);
      alert("Failed to submit order.");
    }
  };

  const handleNext = async () => {
    try {
      if (currentStep === 1) {
        await saveStep1();
        setCurrentStep(2);
      } else if (currentStep === 2) {
        await saveStep2();
        setCurrentStep(3);
      } else if (currentStep === 3) {
        await saveStep3();
        setCurrentStep(4);
      } else if (currentStep === 4) {
        if (fabricTab === 'boutique' && !selectedFabric) {
          alert("Please select a fabric from the catalog or upload your own fabric.");
          return;
        }
        await saveStep4();
        setCurrentStep(5);
      } else if (currentStep === 5) {
        if (!selectedTailor) {
          alert("Please assign a tailor for the creation.");
          return;
        }
        setCurrentStep(6);
      } else if (currentStep === 6) {
        if (!paymentPhase) {
          setPaymentPhase(true);
        } else {
          if (!agreedToTerms) {
            alert("Please agree to the Terms & Conditions and Privacy Policy before placing the order.");
            return;
          }
          await submitOrderAndConfirm();
        }
      }
    } catch (err) {
      console.error("Step execution failed", err);
      if (currentStep !== 1) {
        alert("Failed to proceed: " + err.message);
      }
    }
  };

  const handleSaveDraft = async () => {
    try {
      if (currentStep === 1) {
        await saveStep1();
      } else if (currentStep === 2) {
        await saveStep2();
      } else if (currentStep === 3) {
        await saveStep3();
      } else if (currentStep === 4) {
        await saveStep4();
      }
      alert("Draft saved successfully!");
      setView('dashboard');
      fetchDashboardAndConfig();
    } catch (err) {
      console.error(err);
      alert("Failed to save draft.");
    }
  };

  // Image Upload Handlers
  const handleProfilePhotoChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setProfilePhoto(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setProfilePhotoPreview(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleDesignFilesChange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      setDesignFiles(prev => [...prev, ...files]);
      files.forEach(file => {
        const reader = new FileReader();
        reader.onloadend = () => {
          setDesignPreviews(prev => [...prev, reader.result]);
        };
        reader.readAsDataURL(file);
      });
    }
  };

  const handleFabricFilesChange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      setFabricFiles(prev => [...prev, ...files]);
      files.forEach(file => {
        const reader = new FileReader();
        reader.onloadend = () => {
          setFabricPreviews(prev => [...prev, reader.result]);
        };
        reader.readAsDataURL(file);
      });
    }
  };

  const getSubtotal = () => {
    const base = parseFloat(quotePrices.base || 0);
    const fabricPrice = parseFloat(quotePrices.fabric || 0);
    const embroidery = parseFloat(quotePrices.embroidery || 0);
    const customization = parseFloat(quotePrices.customization || 0);
    const tailoring = parseFloat(quotePrices.tailoring || 0);
    const packaging = parseFloat(quotePrices.packaging || 0);
    return base + fabricPrice + embroidery + customization + tailoring + packaging;
  };

  const getTaxes = () => {
    return getSubtotal() * 0.05;
  };

  const getTotalPrice = () => {
    return getSubtotal() + getTaxes();
  };

  const getPasswordStrength = () => {
    const len = signupForm.password.length;
    if (len === 0) return '';
    if (len < 6) return 'weak';
    if (len < 10) return 'medium';
    return 'strong';
  };

  // Filter lists
  const filteredDashboardCustomers = dashboardData?.recent_customers?.filter(c => {
    const fullName = `${c.first_name} ${c.last_name}`.toLowerCase();
    const query = searchQuery.toLowerCase();
    return fullName.includes(query) || c.mobile_number.includes(query) || c.garment_type.toLowerCase().includes(query);
  }) || [];

  const filteredSearchModalCustomers = allCustomers.filter(c => {
    const fullName = `${c.first_name} ${c.last_name}`.toLowerCase();
    const query = searchModalQuery.toLowerCase();
    return fullName.includes(query) || c.mobile_number.includes(query);
  });

  return (
    <div className="app-container">
      {/* 1. PUBLIC LANDING PAGE (Image 1) */}
      {view === 'landing' && (
        <div className="landing-page">
          <nav className="landing-navbar">
            <div className="brand-logo">TRYON2BUY</div>
            <ul className="landing-nav-links">
              <li><a href="#home">Home</a></li>
              <li><a href="#how">How it Works</a></li>
              <li><a href="#about">About Us</a></li>
              <li><a href="#collections">Collections</a></li>
              <li><a href="#boutique">For Boutiques</a></li>
              <li><a href="#contact">Contact</a></li>
            </ul>
            <div className="landing-nav-actions">
              <button className="btn-secondary" onClick={() => setView('login')}>Login</button>
              <button className="btn-primary" onClick={() => { setSignupStep(1); setView('signup'); }}>Signup</button>
            </div>
          </nav>

          <header className="landing-hero" id="home">
            <h1>Your Vision. Expertly Crafted.</h1>
            <p className="hero-subtitle">Create custom garments that reflect your style. Personalized for you. Perfected by our artisans.</p>
            <div className="hero-cta-group">
              <button className="btn-primary" style={{ padding: '16px 36px', fontSize: '15px' }} onClick={() => setView('login')}>
                Create Your Custom Outfit
                <ArrowRight size={18} />
              </button>
              <a href="#how" className="btn-cta-text">
                HOW IT WORKS
                <HelpCircle size={16} />
              </a>
            </div>
          </header>

          {/* Three introductory points */}
          <div className="landing-features-intro">
            <div className="feat-intro-item">
              <div className="feat-intro-icon"><User size={20} /></div>
              <div className="feat-intro-text">
                <h4>Personalized for you</h4>
                <p>Tailored exclusively to your custom design and size measurements.</p>
              </div>
            </div>
            <div className="feat-intro-item">
              <div className="feat-intro-icon"><Star size={20} /></div>
              <div className="feat-intro-text">
                <h4>Premium Quality</h4>
                <p>Woven with handpicked threads and constructed by master tailors.</p>
              </div>
            </div>
            <div className="feat-intro-item">
              <div className="feat-intro-icon"><ShieldCheck size={20} /></div>
              <div className="feat-intro-text">
                <h4>Secure & Private</h4>
                <p>Your size dimensions and specifications are stored securely.</p>
              </div>
            </div>
          </div>

          {/* How it works */}
          <section className="experience-section" id="how">
            <h2>The TryOn2Buy Experience</h2>
            <p className="sec-desc">A seamless journey from your vision to your doorstep.</p>
            
            <div className="experience-grid">
              <div className="exp-card">
                <div className="exp-icon"><Users size={20} /></div>
                <h4>1. Create Profile</h4>
                <p>Tell us about yourself and style preferences.</p>
              </div>
              <div className="exp-card">
                <div className="exp-icon"><Scissors size={20} /></div>
                <h4>2. Share Measurements</h4>
                <p>Provide accurate body specifications.</p>
              </div>
              <div className="exp-card">
                <div className="exp-icon"><Compass size={20} /></div>
                <h4>3. Design Your Outfit</h4>
                <p>Choose fabric, neckline, sleeves, and sketches.</p>
              </div>
              <div className="exp-card">
                <div className="exp-icon"><Star size={20} /></div>
                <h4>4. Expert Crafting</h4>
                <p>Our tailors execute stitching and quality checks.</p>
              </div>
              <div className="exp-card">
                <div className="exp-icon"><ShoppingBag size={20} /></div>
                <h4>5. Delivered to You</h4>
                <p>Carefully packed and shipped directly to your door.</p>
              </div>
            </div>
          </section>

          {/* Collections Section */}
          <section className="possibilities-section" id="collections">
            <h2>Explore Custom Possibilities</h2>
            <p className="sec-desc">Designed for every occasion and every you.</p>

            <div className="possibilities-grid">
              {[
                { name: 'Lehenga', img: 'https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=300' },
                { name: 'Sherwani', img: 'https://images.unsplash.com/photo-1597983073492-bc24058b375b?w=300' },
                { name: 'Saree', img: 'https://images.unsplash.com/photo-1610030469668-93535c17b6b3?w=300' },
                { name: 'Suit', img: 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=300' },
                { name: 'Kurta Set', img: 'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=300' },
                { name: 'Casual Wear', img: 'https://images.unsplash.com/photo-1578932750294-f5075e85f44a?w=300' }
              ].map((c, idx) => (
                <div className="possibility-card" key={idx}>
                  <div className="possibility-image">
                    <img src={c.img} alt={c.name} />
                  </div>
                  <span>{c.name}</span>
                </div>
              ))}
            </div>

            <button className="btn-secondary" style={{ margin: '0 auto' }}>
              View All Collections
              <ChevronRight size={16} />
            </button>
          </section>

          {/* Stats Bar */}
          <div className="landing-stats-grid">
            <div className="stat-item">
              <div className="stat-item-val">10K+</div>
              <div className="stat-item-label">Happy Customers</div>
              <div className="stat-item-sub">Across India & Abroad</div>
            </div>
            <div className="stat-item">
              <div className="stat-item-val">4.9/5</div>
              <div className="stat-item-label">Customer Rating</div>
              <div className="stat-item-sub">Based on 3,000+ reviews</div>
            </div>
            <div className="stat-item">
              <div className="stat-item-val">100%</div>
              <div className="stat-item-label">Fit Guarantee</div>
              <div className="stat-item-sub">No-cost alterations</div>
            </div>
            <div className="stat-item">
              <div className="stat-item-val">Premium</div>
              <div className="stat-item-label">Quality Handpicked Fabrics</div>
              <div className="stat-item-sub">Sourced dynamically</div>
            </div>
          </div>

          {/* Contact Section */}
          <section className="footer-newsletter-banner" id="contact">
            <div className="newsletter-questions-card">
              <h4>Have questions?</h4>
              <p>Chat with our style experts and bring your vision to life.</p>
              <button className="whatsapp-btn" style={{ marginTop: 'auto', backgroundColor: '#fff', color: '#2b2623' }}>
                <MessageSquare size={16} />
                Chat on WhatsApp
              </button>
            </div>
            <div className="newsletter-subscribe-card">
              <h4>Stay inspired</h4>
              <p>Get style guides, collection drops, and updates sent straight to your inbox.</p>
              <div className="subscribe-form-row">
                <input type="email" placeholder="Enter your email" className="form-control" />
                <button className="btn-primary" style={{ backgroundColor: '#2b2623' }}>Subscribe</button>
              </div>
            </div>
          </section>

          {/* Copyright Footer */}
          <footer className="copyright-footer">
            <div>
              <div className="brand-logo" style={{ fontSize: '18px', marginBottom: '8px' }}>TRYON2BUY</div>
              <div>© 2026 Vastra AI. All rights reserved. Your Vision. Our Craft.</div>
            </div>
            <div className="footer-links">
              <a href="#">Editorial</a>
              <a href="#">Sustainability</a>
              <a href="#">Privacy Policy</a>
              <a href="#">Terms of Use</a>
            </div>
          </footer>
        </div>
      )}

      {/* 2. SIGN IN SCREEN (Image 2) */}
      {view === 'login' && (
        <div className="auth-page">
          <div className="auth-logo">TRYON2BUY</div>
          <div className="auth-logo-sub">YOUR VISION. OUR CRAFT.</div>

          <div className="auth-card">
            <h2 className="auth-title">Welcome back 👋</h2>
            <p className="auth-subtitle">Login to continue your custom creation journey.</p>
            
            <form onSubmit={handleLoginSubmit} className="auth-form">
              <div className="form-group">
                <label className="form-label">Email or Mobile Number</label>
                <div className="input-wrapper">
                  <Mail size={16} className="input-icon-left" />
                  <input 
                    type="text" 
                    placeholder="Enter your email or mobile number"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Password</label>
                <div className="input-wrapper">
                  <Lock size={16} className="input-icon-left" />
                  <input 
                    type={showLoginPassword ? "text" : "password"} 
                    placeholder="Enter your password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    style={{ paddingRight: '40px' }}
                    required
                  />
                  <button 
                    type="button"
                    style={{ position: 'absolute', right: '12px', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}
                    onClick={() => setShowLoginPassword(!showLoginPassword)}
                  >
                    {showLoginPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div className="auth-remember-row">
                <label className="remember-me-checkbox">
                  <input type="checkbox" defaultChecked />
                  Remember me
                </label>
                <a href="#" className="forgot-password-link">Forgot password?</a>
              </div>

              <button type="submit" className="btn-primary" style={{ justifyContent: 'center', padding: '14px' }}>
                Login
              </button>
            </form>

            <div className="divider-container">OR CONTINUE WITH</div>

            <div className="social-auth-buttons">
              <button className="social-btn">
                <Compass size={16} />
                Continue with Google
              </button>
              <button className="social-btn">
                <User size={16} />
                Continue with Apple
              </button>
              <button className="social-btn">
                <MessageSquare size={16} />
                Continue with WhatsApp
              </button>
            </div>

            <div className="accent-banner" style={{ justifyContent: 'center' }}>
              <ShieldCheck size={16} />
              <span><strong>Secure. Private. Yours.</strong> Your personal data and custom preferences are safe with us.</span>
            </div>

            <div className="auth-card-footer">
              Don't have a boutique account? <a href="#" onClick={() => { setSignupStep(1); setView('signup'); }}>Signup</a>
            </div>
          </div>
        </div>
      )}

      {/* 3. SIGN UP SCREEN (Image 3) */}
      {view === 'signup' && (
        <div className="auth-page">
          <div className="auth-logo">TRYON2BUY</div>
          <div className="auth-logo-sub">YOUR VISION. OUR CRAFT.</div>

          {/* Auth Steps Tracker */}
          <div className="auth-steps-tracker">
            {[
              { step: 1, label: 'Account' },
              { step: 2, label: 'Verify' },
              { step: 3, label: 'Profile' },
              { step: 4, label: 'Preferences' },
              { step: 5, label: 'Complete' }
            ].map(item => (
              <div key={item.step} className={`auth-step-item ${signupStep === item.step ? 'active' : ''}`}>
                <div className="auth-step-num">{item.step}</div>
                <span className="auth-step-label">{item.label}</span>
              </div>
            ))}
          </div>

          <div className="auth-card">
            {signupStep === 1 && (
              <>
                <h2 className="auth-title">Create your account</h2>
                <p className="auth-subtitle">Join TryOn2Buy and start your custom creation journey.</p>
                
                <form onSubmit={handleSignupSubmit} className="auth-form">
                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">First Name</label>
                      <input 
                        type="text" 
                        placeholder="Enter first name"
                        value={signupForm.first_name}
                        onChange={(e) => setSignupForm({...signupForm, first_name: e.target.value})}
                        required
                        className="form-control"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Last Name</label>
                      <input 
                        type="text" 
                        placeholder="Enter last name"
                        value={signupForm.last_name}
                        onChange={(e) => setSignupForm({...signupForm, last_name: e.target.value})}
                        required
                        className="form-control"
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Email Address</label>
                    <input 
                      type="email" 
                      placeholder="Enter your email address"
                      value={signupForm.email_address}
                      onChange={(e) => setSignupForm({...signupForm, email_address: e.target.value})}
                      required
                      className="form-control"
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Mobile Number</label>
                    <div className="input-wrapper">
                      <span className="input-icon-left" style={{ left: '12px', fontSize: '14px' }}>+91</span>
                      <input 
                        type="tel" 
                        placeholder="Enter mobile number"
                        value={signupForm.mobile_number}
                        onChange={(e) => setSignupForm({...signupForm, mobile_number: e.target.value})}
                        style={{ paddingLeft: '50px' }}
                        required
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Password</label>
                    <input 
                      type="password" 
                      placeholder="Create a password (min 6 characters)"
                      value={signupForm.password}
                      onChange={(e) => setSignupForm({...signupForm, password: e.target.value})}
                      required
                      className="form-control"
                    />
                    {signupForm.password && (
                      <div className="password-strength-meter">
                        <div className="password-strength-bar">
                          <div className={`password-strength-fill ${getPasswordStrength()}`}></div>
                        </div>
                        <span className="password-strength-text">
                          Password strength: <span>{getPasswordStrength()}</span>
                        </span>
                      </div>
                    )}
                  </div>

                  <label className="remember-me-checkbox" style={{ fontSize: '12px' }}>
                    <input type="checkbox" required />
                    I agree to the Terms & Conditions and Privacy Policy
                  </label>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '12px' }}>
                    <button type="button" className="btn-secondary" style={{ justifyContent: 'center' }} onClick={() => setView('login')}>
                      Login
                    </button>
                    <button type="submit" className="btn-primary" style={{ justifyContent: 'center' }}>
                      Create Account
                    </button>
                  </div>
                </form>

                <div className="divider-container">OR CONTINUE WITH</div>
                <div className="social-icons-row">
                  <div className="social-icon-circle"><Compass size={18} /></div>
                  <div className="social-icon-circle"><User size={18} /></div>
                  <div className="social-icon-circle"><MessageSquare size={18} /></div>
                </div>
              </>
            )}

            {signupStep === 2 && (
              <>
                <h2 className="auth-title">Verify Mobile Number</h2>
                <p className="auth-subtitle">We have sent a 6-digit OTP code to +91 {signupForm.mobile_number}</p>
                
                <div className="auth-form">
                  <div className="form-group">
                    <label className="form-label">Verification Code (OTP)</label>
                    <input 
                      type="text" 
                      maxLength="6"
                      placeholder="Enter 6-digit code"
                      className="form-control"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value)}
                      style={{ textAlign: 'center', letterSpacing: '8px', fontSize: '20px' }}
                    />
                  </div>

                  <button className="btn-primary" style={{ justifyContent: 'center' }} onClick={handleVerifyOTP}>
                    Verify OTP
                  </button>
                  <button className="btn-secondary" style={{ justifyContent: 'center' }} onClick={() => setSignupStep(1)}>
                    Back
                  </button>
                </div>
              </>
            )}

            {signupStep === 3 && (
              <>
                <h2 className="auth-title">Complete Profile</h2>
                <p className="auth-subtitle">Tell us about your boutique role and communication channel.</p>
                
                <div className="auth-form">
                  <div className="form-group">
                    <label className="form-label">Occupation / Role</label>
                    <input 
                      type="text" 
                      placeholder="e.g. Master Stylist, Atelier Director"
                      className="form-control"
                      value={profileOccupation}
                      onChange={(e) => setProfileOccupation(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Preferred Communication channel</label>
                    <select 
                      className="form-control"
                      value={profileComm}
                      onChange={(e) => setProfileComm(e.target.value)}
                    >
                      <option value="WhatsApp">WhatsApp</option>
                      <option value="Call">Phone Call</option>
                      <option value="Email">Email</option>
                    </select>
                  </div>

                  <button className="btn-primary" style={{ justifyContent: 'center' }} onClick={handleProfileSubmit}>
                    Next: Customizer Prefs
                  </button>
                </div>
              </>
            )}

            {signupStep === 4 && (
              <>
                <h2 className="auth-title">Design Style Preferences</h2>
                <p className="auth-subtitle">Select style tags that correspond to your boutique specialization.</p>
                
                <div className="auth-form">
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', margin: '16px 0' }}>
                    {['Bridal Lehenga', 'Embroidery Gowns', 'Mens Sherwani', 'Premium Silk Sarees', 'Designer Kurta Sets', 'Western Suits'].map(tag => (
                      <span 
                        key={tag} 
                        style={{ 
                          padding: '8px 16px', 
                          borderRadius: '99px', 
                          border: '1px solid #b07c40', 
                          backgroundColor: '#fcf6ee',
                          color: '#b07c40',
                          fontSize: '12px',
                          fontWeight: '600'
                        }}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>

                  <button className="btn-primary" style={{ justifyContent: 'center' }} onClick={handleCompleteRegistration}>
                    Submit Registration
                  </button>
                </div>
              </>
            )}

            {signupStep === 5 && (
              <div style={{ textAlign: 'center', padding: '32px' }}>
                <div className="success-circle" style={{ margin: '0 auto 20px' }}><Check size={36} /></div>
                <h2 className="auth-title">Registration Complete!</h2>
                <p style={{ color: 'var(--text-secondary)' }}>Welcome to TryOn2Buy. Redirecting you to the portal workspace...</p>
              </div>
            )}
          </div>

          <div className="auth-badge-info-grid">
            <div className="auth-badge-card">
              <Lock className="auth-badge-icon" size={24} />
              <h4>Secure & Encrypted</h4>
              <p>Your data is protected with enterprise-tier bank level security standards.</p>
            </div>
            <div className="auth-badge-card">
              <Compass className="auth-badge-icon" size={24} />
              <h4>Personalized Experience</h4>
              <p>Tailored custom order builders matching style flows perfectly.</p>
            </div>
            <div className="auth-badge-card">
              <Star className="auth-badge-icon" size={24} />
              <h4>Expert Support</h4>
              <p>Boutique assistance is available 24/7 at the click of a button.</p>
            </div>
          </div>
        </div>
      )}

      {/* 4. BOUTIQUE PORTAL MAIN WORKSPACE (Image 4) */}
      {view === 'dashboard' && currentUser && (
        <div className="portal-layout">
          {/* Sidebar */}
          <aside className="portal-sidebar">
            <div className="portal-sidebar-logo">TRYON2BUY</div>
            <div className="portal-sidebar-logo-sub">THE ATELIER EXPERIENCE</div>
            
            <nav className="portal-menu">
              <a className={`portal-menu-item ${dashboardTab === 'overview' ? 'active' : ''}`} onClick={() => setDashboardTab('overview')}><Users size={16} /> Dashboard</a>
              <a className={`portal-menu-item ${dashboardTab === 'customers' ? 'active' : ''}`} onClick={() => setDashboardTab('customers')}><Users size={16} /> Customers</a>
              <a className={`portal-menu-item ${dashboardTab === 'invoices' ? 'active' : ''}`} onClick={() => setDashboardTab('invoices')}><FileText size={16} /> Invoices</a>
              <a className={`portal-menu-item ${dashboardTab === 'analytics' ? 'active' : ''}`} onClick={() => setDashboardTab('analytics')}><BarChart2 size={16} /> Analytics</a>
              <a className={`portal-menu-item ${dashboardTab === 'fabrics' ? 'active' : ''}`} onClick={() => setDashboardTab('fabrics')}><Compass size={16} /> Manage Fabrics</a>
              <a className={`portal-menu-item ${dashboardTab === 'tailors' ? 'active' : ''}`} onClick={() => setDashboardTab('tailors')}><Scissors size={16} /> Manage Tailors</a>
              <a className={`portal-menu-item ${dashboardTab === 'designs' ? 'active' : ''}`} onClick={() => setDashboardTab('designs')}><Sparkles size={16} /> Manage Designs</a>
              <a className={`portal-menu-item ${dashboardTab === 'account' ? 'active' : ''}`} onClick={() => setDashboardTab('account')}><User size={16} /> My Account</a>
              <a className="portal-menu-item" onClick={handleLogout}><LogOut size={16} /> Logout</a>
            </nav>

            <div className="portal-sidebar-footer">
              <div className="portal-sidebar-help">
                <h4 style={{ fontSize: '12px', fontWeight: 700 }}>Need Help?</h4>
                <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Our style concierge is here to assist you.</p>
                <button 
                  className="whatsapp-btn" 
                  style={{ width: '100%', padding: '6px', fontSize: '11px' }}
                  onClick={() => window.open('https://wa.me/919876543210')}
                >
                  <MessageSquare size={12} />
                  Chat Now
                </button>
              </div>
            </div>
          </aside>

          {/* Main Content Area */}
          <main className="portal-main">
            {dashboardTab === 'overview' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        Welcome back, {currentUser.first_name}! 👋
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Your custom creation journey starts here.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <button className="btn-primary" onClick={() => setView('order-selector')}>
                      <Sparkles size={16} />
                      New Custom Order
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
                    </div>
                  </div>
                </header>

                {/* Quick Action Grid */}
                <section className="quick-action-button-grid">
                  <div className="quick-action-item" onClick={() => setView('order-selector')}>
                    <div className="quick-action-icon-box"><ShoppingBag size={18} /></div>
                    <h4>New Order</h4>
                    <p>Start custom order</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setDashboardTab('tailors')}>
                    <div className="quick-action-icon-box"><Scissors size={18} /></div>
                    <h4>Manage Staff</h4>
                    <p>Tailors & status</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setDashboardTab('designs')}>
                    <div className="quick-action-icon-box"><Heart size={18} /></div>
                    <h4>Design Catalog</h4>
                    <p>Style collections</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setDashboardTab('fabrics')}>
                    <div className="quick-action-icon-box"><Compass size={18} /></div>
                    <h4>Fabric Library</h4>
                    <p>Explore fabrics</p>
                  </div>
                  <div className="quick-action-item">
                    <div className="quick-action-icon-box"><Calendar size={18} /></div>
                    <h4>Book Appointment</h4>
                    <p>Consult with stylist</p>
                  </div>
                </section>

                {/* Row Layout: Orders & Progress Tracker */}
                <div className="dashboard-row-layout">
                  {/* Active Orders List */}
                  <div className="orders-list-panel">
                    <div className="panel-header-row">
                      <h3 style={{ fontSize: '16px', fontWeight: 600 }}>My Orders</h3>
                      <a href="#" className="view-all-link">VIEW ALL ORDERS →</a>
                    </div>

                    {loading ? (
                      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                        Loading active orders...
                      </div>
                    ) : !dashboardData?.recent_orders || dashboardData.recent_orders.length === 0 ? (
                      <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No active custom orders. Click "New Custom Order" to begin!
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        {dashboardData.recent_orders.map(order => (
                          <div 
                            key={order.id} 
                            className={`order-row-card ${selectedDashboardOrder?.id === order.id ? 'active-border' : ''}`}
                            onClick={() => setSelectedDashboardOrder(order)}
                            style={{
                              borderColor: selectedDashboardOrder?.id === order.id ? 'var(--text-primary)' : 'var(--border-color)'
                            }}
                          >
                            <div className="order-row-thumbnail">
                              <img 
                                src="https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=100" 
                                alt="Garment Thumbnail" 
                              />
                            </div>
                            <div className="order-row-desc">
                              <div className="order-row-id">Order ID: {order.order_id}</div>
                              <div className="order-row-name">{order.customer_name} • {order.order_status}</div>
                              <div className="order-row-fabric">Tailor: {order.tailor_name || 'Unassigned'}</div>
                            </div>
                            <div className="order-row-status-box">
                              <span className={`order-row-badge ${order.order_status === 'Confirmed' ? 'confirmed' : 'in_progress'}`}>
                                {order.order_status === 'Confirmed' ? 'Confirmed' : 'In Progress'}
                              </span>
                              <span className="order-row-date">Est. {new Date(order.estimated_delivery).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Order Live Tracker Sidebar */}
                  <div className="order-detail-progress-card">
                    <div className="panel-header-row">
                      <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Order Progress</h3>
                      <a href="#" className="view-all-link">VIEW ALL</a>
                    </div>

                    {selectedDashboardOrder ? (
                      <>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <div style={{ fontSize: '13px', fontWeight: 600 }}>{selectedDashboardOrder.customer_name}</div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Order ID: {selectedDashboardOrder.order_id}</div>
                        </div>

                        <div className="order-progress-steps-list">
                          {(() => {
                            const stages = ['Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Packed & Shipped', 'Delivered'];
                            const currentIdx = stages.indexOf(selectedDashboardOrder.order_status);
                            
                            return stages.map((title, idx) => {
                              let state = 'upcoming';
                              let sub = 'Upcoming';
                              
                              if (idx < currentIdx) {
                                state = 'completed';
                                if (title === 'Confirmed') {
                                  sub = new Date(selectedDashboardOrder.order_date).toLocaleDateString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
                                } else {
                                  sub = 'Completed';
                                }
                              } else if (idx === currentIdx) {
                                state = 'current';
                                sub = 'In Progress';
                              }
                              
                              return (
                                <div key={idx} className={`progress-step-item ${state === 'completed' ? 'completed' : state === 'current' ? 'active' : ''}`}>
                                  <div className="progress-step-dot"></div>
                                  <div className="progress-step-info">
                                    <span className="progress-step-title">{title === 'Confirmed' ? 'Order Confirmed' : title}</span>
                                    <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{sub}</span>
                                  </div>
                                  <span className={`progress-step-state-tag ${state === 'completed' ? 'completed' : state === 'current' ? 'current' : ''}`}>
                                    {state === 'completed' ? 'Completed' : state === 'current' ? 'In Progress' : ''}
                                  </span>
                                </div>
                              );
                            });
                          })()}
                        </div>

                        <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid var(--border-color, rgba(255,255,255,0.08))', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: '12px', fontWeight: 600 }}>Update Status:</span>
                            <select 
                              value={selectedDashboardOrder.order_status} 
                              onChange={async (e) => {
                                const newStatus = e.target.value;
                                try {
                                  await api.updateOrderStatus(selectedDashboardOrder.id, newStatus);
                                  setSelectedDashboardOrder(prev => ({ ...prev, order_status: newStatus }));
                                  fetchDashboardAndConfig();
                                } catch (err) {
                                  alert("Failed to update status: " + err.message);
                                }
                              }}
                              style={{
                                background: 'rgba(255,255,255,0.05)',
                                color: '#fff',
                                border: '1px solid rgba(255,255,255,0.15)',
                                borderRadius: '6px',
                                padding: '4px 8px',
                                fontSize: '12px',
                                cursor: 'pointer'
                              }}
                            >
                              {['Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Packed & Shipped', 'Delivered'].map(status => (
                                <option key={status} value={status} style={{ background: '#222', color: '#fff' }}>{status}</option>
                              ))}
                            </select>
                          </div>
                          
                          {selectedDashboardOrder.order_status !== 'Delivered' && (
                            <button 
                              className="btn-primary" 
                              style={{ fontSize: '12px', padding: '8px 12px', justifyContent: 'center', width: '100%' }}
                              onClick={async () => {
                                const stages = ['Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Packed & Shipped', 'Delivered'];
                                const currentIndex = stages.indexOf(selectedDashboardOrder.order_status);
                                if (currentIndex !== -1 && currentIndex < 5) {
                                  const nextStatus = stages[currentIndex + 1];
                                  try {
                                    await api.updateOrderStatus(selectedDashboardOrder.id, nextStatus);
                                    setSelectedDashboardOrder(prev => ({ ...prev, order_status: nextStatus }));
                                    fetchDashboardAndConfig();
                                  } catch (err) {
                                    alert("Failed to update status: " + err.message);
                                  }
                                }
                              }}
                            >
                              Advance to Next Stage
                            </button>
                          )}
                        </div>
                      </>
                    ) : (
                      <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '12px' }}>
                        Select an order on the left to see progress details.
                      </div>
                    )}
                  </div>
                </div>

                {/* Upcoming Appointments & Style Inspiration Row */}
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '32px' }}>
                  <div>
                    <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Upcoming Appointments</h3>
                    <div className="appointments-section-panel">
                      <div className="appt-card">
                        <div className="appt-date-box">
                          <span className="appt-day">31</span>
                          <span className="appt-month">May</span>
                        </div>
                        <div className="appt-info">
                          <span className="appt-title">Styling Consultation</span>
                          <span className="appt-sub">with Anya (Stylist)</span>
                          <span className="appt-time">05:00 PM — 05:30 PM</span>
                        </div>
                      </div>
                      <div className="appt-card">
                        <div className="appt-date-box">
                          <span className="appt-day">07</span>
                          <span className="appt-month">Jun</span>
                        </div>
                        <div className="appt-info">
                          <span className="appt-title">Measurement Review</span>
                          <span className="appt-sub">with Rohit (Master Tailor)</span>
                          <span className="appt-time">11:00 AM — 11:30 AM</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Style Inspiration</h3>
                    <div className="inspiration-grid-row">
                      <div className="inspiration-circle-avatar">
                        <img src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100" alt="Insp1" />
                      </div>
                      <div className="inspiration-circle-avatar">
                        <img src="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100" alt="Insp2" />
                      </div>
                      <div className="inspiration-circle-avatar">
                        <img src="https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100" alt="Insp3" />
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* 2. MANAGE FABRICS TAB */}
            {dashboardTab === 'fabrics' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        Manage Fabric Library
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Configure, add, or edit boutique catalog fabrics.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <button className="btn-primary" onClick={() => {
                      setEditingFabric(null);
                      setFabricForm({ name: '', material: '', color: '', price_per_meter: '', image_url: '', is_available: true });
                      setShowFabricModal(true);
                    }}>
                      <Plus size={16} />
                      Add New Fabric
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
                    </div>
                  </div>
                </header>

                <div className="fabric-manager-content" style={{ marginTop: '24px' }}>
                  <div className="fabrics-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '24px' }}>
                    {fabrics.map(fabric => (
                      <div key={fabric.id} className="fabric-manage-card" style={{
                        background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                        border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                        borderRadius: '12px',
                        padding: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        gap: '16px'
                      }}>
                        <div style={{ display: 'flex', gap: '16px' }}>
                          <div className="fabric-image-swatch" style={{
                            width: '80px',
                            height: '80px',
                            borderRadius: '8px',
                            overflow: 'hidden',
                            background: fabric.color ? fabric.color.toLowerCase() : '#ccc',
                            flexShrink: 0,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            border: '1px solid rgba(255,255,255,0.1)'
                          }}>
                            {fabric.image_url ? (
                              <img src={fabric.image_url} alt={fabric.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            ) : (
                              <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#fff', fontWeight: 600, textShadow: '1px 1px 2px rgba(0,0,0,0.5)' }}>
                                {fabric.color}
                              </span>
                            )}
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            <h4 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{fabric.name}</h4>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Material: {fabric.material}</span>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Color: {fabric.color}</span>
                            <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--accent-color, #d4af37)', marginTop: '4px' }}>
                              ₹{parseFloat(fabric.price_per_meter).toLocaleString('en-IN')}/mtr
                            </span>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '12px' }}>
                          <span className={`order-row-badge ${fabric.is_available ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
                            {fabric.is_available ? 'Available' : 'Out of Stock'}
                          </span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => {
                              setEditingFabric(fabric);
                              setFabricForm({
                                name: fabric.name,
                                material: fabric.material,
                                color: fabric.color,
                                price_per_meter: fabric.price_per_meter.toString(),
                                image_url: fabric.image_url || '',
                                is_available: fabric.is_available
                              });
                              setShowFabricModal(true);
                            }}>
                              <Edit2 size={12} /> Edit
                            </button>
                            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px', color: '#ff4d4d', borderColor: 'rgba(255,77,77,0.2)' }} onClick={() => handleDeleteFabric(fabric.id)}>
                              <Trash2 size={12} /> Delete
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* 3. MANAGE TAILORS TAB */}
            {dashboardTab === 'tailors' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        Manage Tailoring Staff
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Add, configure, or review in-house custom tailors.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <button className="btn-primary" onClick={() => {
                      setEditingTailor(null);
                      setTailorForm({ name: '', specialty: '', rating: 5.0, status: 'Available' });
                      setShowTailorModal(true);
                    }}>
                      <Plus size={16} />
                      Add New Tailor
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
                    </div>
                  </div>
                </header>

                <div className="tailor-manager-content" style={{ marginTop: '24px' }}>
                  <div className="tailors-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '24px' }}>
                    {tailors.map(tailor => (
                      <div key={tailor.id} className="tailor-manage-card" style={{
                        background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                        border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                        borderRadius: '12px',
                        padding: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        gap: '16px'
                      }}>
                        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                          <div className="tailor-avatar" style={{
                            width: '60px',
                            height: '60px',
                            borderRadius: '50%',
                            background: 'var(--border-color, rgba(255,255,255,0.08))',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '20px',
                            fontWeight: 600,
                            color: 'var(--accent-color, #d4af37)',
                            overflow: 'hidden'
                          }}>
                            <img 
                              src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(tailor.name)}`} 
                              alt={tailor.name} 
                              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                            <h4 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{tailor.name}</h4>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Specialty: {tailor.specialty}</span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                              <Star size={12} fill="#d4af37" color="#d4af37" />
                              <span style={{ fontSize: '12px', fontWeight: 600 }}>{parseFloat(tailor.rating).toFixed(1)}</span>
                            </div>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '12px' }}>
                          <span className={`order-row-badge ${tailor.status === 'Available' ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
                            {tailor.status}
                          </span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => {
                              setEditingTailor(tailor);
                              setTailorForm({
                                name: tailor.name,
                                specialty: tailor.specialty,
                                rating: tailor.rating.toString(),
                                status: tailor.status
                              });
                              setShowTailorModal(true);
                            }}>
                              <Edit2 size={12} /> Edit
                            </button>
                            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px', color: '#ff4d4d', borderColor: 'rgba(255,77,77,0.2)' }} onClick={() => handleDeleteTailor(tailor.id)}>
                              <Trash2 size={12} /> Delete
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* 4. MANAGE DESIGNS TAB */}
            {dashboardTab === 'designs' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        Manage Design Collections
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Add, edit, or remove catalog designs and AI suggestions.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <button className="btn-primary" onClick={() => {
                      setEditingDesign(null);
                      setDesignForm({
                        name: '',
                        garment_type: 'Lehenga',
                        neckline_style: '',
                        sleeve_style: '',
                        image_url: '',
                        is_boutique: true,
                        price: 0,
                        description: ''
                      });
                      setShowDesignModal(true);
                    }}>
                      <Plus size={16} />
                      Add New Design
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
                    </div>
                  </div>
                </header>

                <div className="design-manager-content" style={{ marginTop: '24px' }}>
                  <div className="designs-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '24px' }}>
                    {allDesigns.map(design => (
                      <div key={design.id} className="design-manage-card" style={{
                        background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                        border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                        borderRadius: '12px',
                        overflow: 'hidden',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between'
                      }}>
                        <div>
                          <div className="design-card-thumbnail" style={{
                            width: '100%',
                            height: '180px',
                            background: '#222',
                            position: 'relative',
                            overflow: 'hidden'
                          }}>
                            <img 
                              src={design.image_url || 'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400'} 
                              alt={design.name} 
                              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                            <span style={{
                              position: 'absolute',
                              top: '12px',
                              right: '12px',
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '10px',
                              fontWeight: 600,
                              textTransform: 'uppercase',
                              background: design.is_boutique ? 'rgba(212, 175, 55, 0.9)' : 'rgba(74, 144, 226, 0.9)',
                              color: '#fff'
                            }}>
                              {design.is_boutique ? 'Boutique Catalog' : 'AI Template'}
                            </span>
                          </div>
                          
                          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                              <h4 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{design.name}</h4>
                            </div>
                            
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', margin: '4px 0' }}>
                              <span style={{ background: 'rgba(255,255,255,0.05)', fontSize: '10px', padding: '2px 6px', borderRadius: '4px' }}>
                                Garment: {design.garment_type}
                              </span>
                              {design.neckline_style && (
                                <span style={{ background: 'rgba(255,255,255,0.05)', fontSize: '10px', padding: '2px 6px', borderRadius: '4px' }}>
                                  Neck: {design.neckline_style}
                                </span>
                              )}
                              {design.sleeve_style && (
                                <span style={{ background: 'rgba(255,255,255,0.05)', fontSize: '10px', padding: '2px 6px', borderRadius: '4px' }}>
                                  Sleeve: {design.sleeve_style}
                                </span>
                              )}
                            </div>
                            
                            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0', lineHeight: 1.4 }}>
                              {design.description || 'No style description provided.'}
                            </p>
                          </div>
                        </div>

                        <div style={{ padding: '16px', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <span style={{ fontSize: '15px', fontWeight: 600, color: 'var(--accent-color, #d4af37)' }}>
                            {design.is_boutique ? `₹${parseFloat(design.price).toLocaleString('en-IN')}` : 'AI Suggestion'}
                          </span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => {
                              setEditingDesign(design);
                              setDesignForm({
                                name: design.name,
                                garment_type: design.garment_type,
                                neckline_style: design.neckline_style || '',
                                sleeve_style: design.sleeve_style || '',
                                image_url: design.image_url || '',
                                is_boutique: design.is_boutique,
                                price: design.price.toString(),
                                description: design.description || ''
                              });
                              setShowDesignModal(true);
                            }}>
                              <Edit2 size={12} /> Edit
                            </button>
                            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px', color: '#ff4d4d', borderColor: 'rgba(255,77,77,0.2)' }} onClick={() => handleDeleteDesign(design.id)}>
                              <Trash2 size={12} /> Delete
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* 5. CUSTOMERS TAB */}
            {dashboardTab === 'customers' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        Customer Directory
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>View client profiles, style files, and body measurements.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <div className="search-input-wrapper" style={{ margin: 0 }}>
                      <Search size={18} />
                      <input 
                        type="text" 
                        placeholder="Search customers..." 
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="form-control"
                        style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
                      />
                    </div>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
                    </div>
                  </div>
                </header>

                <div className="customers-list-container" style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {customersList.filter(cust => {
                    const term = searchQuery.toLowerCase();
                    return (cust.first_name + ' ' + cust.last_name).toLowerCase().includes(term) ||
                           cust.mobile_number.includes(term) ||
                           (cust.email_address && cust.email_address.toLowerCase().includes(term));
                  }).length === 0 ? (
                    <div style={{ padding: '48px', textAlign: 'center', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                      <span style={{ color: 'var(--text-muted)' }}>No customers found matching "{searchQuery}"</span>
                    </div>
                  ) : (
                    customersList.filter(cust => {
                      const term = searchQuery.toLowerCase();
                      return (cust.first_name + ' ' + cust.last_name).toLowerCase().includes(term) ||
                             cust.mobile_number.includes(term) ||
                             (cust.email_address && cust.email_address.toLowerCase().includes(term));
                    }).map(cust => (
                      <div key={cust.id} className="customer-detail-card" style={{
                        background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                        border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                        borderRadius: '12px',
                        padding: '24px',
                        display: 'grid',
                        gridTemplateColumns: '1fr 1.5fr 1.5fr',
                        gap: '24px'
                      }}>
                        {/* Profile Info */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                            <div className="user-avatar-circle" style={{ width: '56px', height: '56px' }}>
                              <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(cust.first_name)}`} alt="Profile" />
                            </div>
                            <div>
                              <h4 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>{cust.first_name} {cust.last_name}</h4>
                              <span style={{ fontSize: '12px', color: 'var(--accent-color, #d4af37)', textTransform: 'uppercase', fontWeight: 600 }}>{cust.customer_type}</span>
                            </div>
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '13px', color: 'var(--text-secondary)', marginTop: '8px' }}>
                            <div>📞 {cust.mobile_number}</div>
                            {cust.email_address && <div>✉️ {cust.email_address}</div>}
                            {cust.address && <div>📍 {cust.address}, {cust.city_region}</div>}
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>Registered: {new Date(cust.created_at).toLocaleDateString()}</div>
                          </div>
                        </div>

                        {/* Measurements */}
                        <div style={{ borderLeft: '1px solid rgba(255,255,255,0.05)', paddingLeft: '24px' }}>
                          <h5 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Body Measurements</h5>
                          {cust.measurements ? (
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px', fontSize: '13px' }}>
                              <div>Bust: <span style={{ fontWeight: 600 }}>{cust.measurements.bust || '—'} in</span></div>
                              <div>Waist: <span style={{ fontWeight: 600 }}>{cust.measurements.waist || '—'} in</span></div>
                              <div>Hips: <span style={{ fontWeight: 600 }}>{cust.measurements.hips || '—'} in</span></div>
                              <div>Shoulder: <span style={{ fontWeight: 600 }}>{cust.measurements.shoulder || '—'} in</span></div>
                              <div>Arm: <span style={{ fontWeight: 600 }}>{cust.measurements.arm_length || '—'} in</span></div>
                              <div>Neck: <span style={{ fontWeight: 600 }}>{cust.measurements.neck || '—'} in</span></div>
                              <div>Length: <span style={{ fontWeight: 600 }}>{cust.measurements.length || '—'} in</span></div>
                            </div>
                          ) : (
                            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No size measurements logged yet.</span>
                          )}
                        </div>

                        {/* Preferences */}
                        <div style={{ borderLeft: '1px solid rgba(255,255,255,0.05)', paddingLeft: '24px' }}>
                          <h5 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Bespoke Profile</h5>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', fontSize: '12px' }}>
                            <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Garment: {cust.garment_type}</span>
                            {cust.neckline_style && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Neck: {cust.neckline_style}</span>}
                            {cust.sleeve_style && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Sleeve: {cust.sleeve_style}</span>}
                            {cust.silhouette && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Silhouette: {cust.silhouette}</span>}
                            {cust.occasion && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Occasion: {cust.occasion}</span>}
                          </div>
                          {cust.custom_requirements && (
                            <div style={{ marginTop: '12px' }}>
                              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Special Requests:</span>
                              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '2px 0 0 0', lineHeight: 1.4 }}>{cust.custom_requirements}</p>
                            </div>
                          )}
                        </div>

                        {/* Style DNA Expand Button */}
                        <div style={{ gridColumn: 'span 3', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Sparkles size={16} style={{ color: 'var(--accent-color, #d4af37)' }} />
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>AI Customer Intelligence has analyzed {cust.orders?.length || 0} order(s) and preferences.</span>
                          </div>
                          <button 
                            className="btn-outline" 
                            onClick={() => setExpandedDna(prev => ({ ...prev, [cust.id]: !prev[cust.id] }))}
                            style={{
                              padding: '6px 14px',
                              fontSize: '12px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px',
                              borderColor: 'rgba(212, 175, 55, 0.4)',
                              color: 'var(--accent-color, #d4af37)',
                              background: expandedDna[cust.id] ? 'rgba(212, 175, 55, 0.1)' : 'transparent',
                              borderRadius: '6px',
                              cursor: 'pointer'
                            }}
                          >
                            <Sparkles size={14} />
                            {expandedDna[cust.id] ? 'Hide Style DNA' : 'View Style DNA'}
                          </button>
                        </div>

                        {/* Expandable Style DNA Section */}
                        {expandedDna[cust.id] && (
                          <div style={{
                            gridColumn: 'span 3',
                            background: '#0d0d0d',
                            border: '1px solid rgba(212, 175, 55, 0.25)',
                            borderRadius: '8px',
                            padding: '24px',
                            marginTop: '12px',
                            display: 'grid',
                            gridTemplateColumns: '1fr 1.2fr',
                            gap: '32px'
                          }}>
                            {/* Left Column: Priya's Style Profile (Mockup Left Card) */}
                            <div style={{
                              background: '#141414',
                              borderRadius: '8px',
                              border: '1px solid rgba(255, 255, 255, 0.05)',
                              overflow: 'hidden'
                            }}>
                              {/* Title Header */}
                              <div style={{
                                background: '#e05a10',
                                padding: '12px 20px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '10px'
                              }}>
                                <User size={18} style={{ color: '#fff' }} />
                                <span style={{
                                  color: '#fff',
                                  fontWeight: 700,
                                  fontSize: '14px',
                                  textTransform: 'uppercase',
                                  letterSpacing: '1px'
                                }}>
                                  {cust.first_name}'s Style Profile
                                </span>
                              </div>
                              
                              {/* Details Table */}
                              <div style={{ padding: '8px 20px' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                                  <tbody>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600, width: '40%' }}>BUDGET</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>{cust.style_dna?.budget}</td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>COLORS</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>
                                        {cust.style_dna?.colors.split(' ').map((word, idx) => {
                                          if (word.includes('%')) return <span key={idx} style={{ color: 'var(--text-muted)', marginRight: '12px', fontWeight: 400 }}>{word} </span>;
                                          // Color highlights
                                          let color = '#fff';
                                          if (word.toLowerCase().includes('blue')) color = '#60a5fa';
                                          else if (word.toLowerCase().includes('green')) color = '#34d399';
                                          else if (word.toLowerCase().includes('red') || word.toLowerCase().includes('maroon')) color = '#f87171';
                                          else if (word.toLowerCase().includes('gold')) color = '#fbbf24';
                                          else if (word.toLowerCase().includes('rose')) color = '#f472b6';
                                          else if (word.toLowerCase().includes('ivory') || word.toLowerCase().includes('white')) color = '#f3f4f6';
                                          else if (word.toLowerCase().includes('black') || word.toLowerCase().includes('charcoal')) color = '#9ca3af';
                                          return <span key={idx} style={{ color }}>{word} </span>;
                                        })}
                                      </td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>STYLE</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>{cust.style_dna?.style}</td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>SIZE</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>{cust.style_dna?.size}</td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>VISIT PATTERN</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>{cust.style_dna?.visit_pattern}</td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>RISK STATUS</td>
                                      <td style={{ padding: '12px 0', fontWeight: 600, color: cust.style_dna?.risk_level === 'danger' ? '#f87171' : cust.style_dna?.risk_level === 'warning' ? '#fbbf24' : '#34d399' }}>
                                        {cust.style_dna?.risk_status.includes('Active') ? '🟢 ' : '⚠️ '}
                                        {cust.style_dna?.risk_status}
                                      </td>
                                    </tr>
                                    <tr>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>NEXT ACTION</td>
                                      <td style={{ padding: '12px 0', color: 'var(--accent-color, #d4af37)', fontWeight: 600 }}>"{cust.style_dna?.next_action}"</td>
                                    </tr>
                                  </tbody>
                                </table>
                                
                                <div style={{
                                  padding: '12px 0 16px 0',
                                  fontSize: '11px',
                                  color: 'var(--text-muted)',
                                  fontStyle: 'italic',
                                  borderTop: '1px solid rgba(255,255,255,0.05)',
                                  marginTop: '8px'
                                }}>
                                  This is NOT manual entry. AI reads your sales data automatically.
                                </div>
                              </div>
                            </div>

                            {/* Right Column: How it Works (Mockup Right Side) */}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', justifyContent: 'center' }}>
                              <div>
                                <h4 style={{
                                  color: '#e05a10',
                                  fontSize: '11px',
                                  fontWeight: 600,
                                  textTransform: 'uppercase',
                                  letterSpacing: '1.5px',
                                  margin: '0 0 16px 0'
                                }}>
                                  AI CUSTOMER INTELLIGENCE
                                </h4>
                                <h3 style={{
                                  fontFamily: 'var(--font-serif)',
                                  fontSize: '24px',
                                  fontWeight: 400,
                                  color: '#fff',
                                  margin: 0
                                }}>
                                  Style DNA — Auto-Generated
                                </h3>
                              </div>

                              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                {/* Row 1 */}
                                <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                                  <div style={{
                                    background: 'rgba(224, 90, 16, 0.1)',
                                    borderRadius: '6px',
                                    padding: '8px',
                                    color: '#e05a10',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                  }}>
                                    <FileText size={18} />
                                  </div>
                                  <div>
                                    <h5 style={{ fontSize: '13px', fontWeight: 600, color: '#fff', margin: '0 0 4px 0' }}>Reads Sales Data</h5>
                                    <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0, lineHeight: 1.4 }}>
                                      AI analyzes every purchase, note, and customer behavior pattern.
                                    </p>
                                  </div>
                                </div>

                                {/* Row 2 */}
                                <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                                  <div style={{
                                    background: 'rgba(224, 90, 16, 0.1)',
                                    borderRadius: '6px',
                                    padding: '8px',
                                    color: '#e05a10',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                  }}>
                                    <Sparkles size={18} />
                                  </div>
                                  <div>
                                    <h5 style={{ fontSize: '13px', fontWeight: 600, color: '#fff', margin: '0 0 4px 0' }}>Builds Style Profile</h5>
                                    <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0, lineHeight: 1.4 }}>
                                      Automatically creates a unique DNA for each customer's preferences.
                                    </p>
                                  </div>
                                </div>

                                {/* Row 3 */}
                                <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                                  <div style={{
                                    background: 'rgba(224, 90, 16, 0.1)',
                                    borderRadius: '6px',
                                    padding: '8px',
                                    color: '#e05a10',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                  }}>
                                    <Calendar size={18} />
                                  </div>
                                  <div>
                                    <h5 style={{ fontSize: '13px', fontWeight: 600, color: '#fff', margin: '0 0 4px 0' }}>Predicts Next Purchase</h5>
                                    <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0, lineHeight: 1.4 }}>
                                      Forecasts what each customer will buy next and when they'll return.
                                    </p>
                                  </div>
                                </div>

                                {/* Row 4 */}
                                <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                                  <div style={{
                                    background: 'rgba(224, 90, 16, 0.1)',
                                    borderRadius: '6px',
                                    padding: '8px',
                                    color: '#e05a10',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                  }}>
                                    <MessageSquare size={18} />
                                  </div>
                                  <div>
                                    <h5 style={{ fontSize: '13px', fontWeight: 600, color: '#fff', margin: '0 0 4px 0' }}>Acts Automatically</h5>
                                    <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0, lineHeight: 1.4 }}>
                                      Sends personalized messages, offers, and recommendations — no manual work.
                                    </p>
                                  </div>
                                </div>
                              </div>

                              <div style={{
                                background: 'rgba(224, 90, 16, 0.05)',
                                border: '1px solid rgba(224, 90, 16, 0.15)',
                                borderRadius: '6px',
                                padding: '12px 16px',
                                fontSize: '12px',
                                color: 'var(--text-muted)',
                                marginTop: '8px'
                              }}>
                                <strong style={{ color: 'var(--accent-color, #d4af37)' }}>500+ data points analyzed</strong> per customer to build the most accurate profile possible.
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                    ))
                  )}
                </div>
              </>
            )}

            {/* 6. INVOICES TAB */}
            {dashboardTab === 'invoices' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        Invoices & Billing
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Manage invoices, verify billing payments, and print receipts.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
                    </div>
                  </div>
                </header>

                <div className="invoices-content" style={{ marginTop: '24px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.02)' }}>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Invoice ID</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Billing Client</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Date</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Subtotal</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Taxes (5% GST)</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Total Price</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Payment Status</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ordersList.length === 0 ? (
                        <tr>
                          <td colSpan="8" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>No invoices or orders recorded yet.</td>
                        </tr>
                      ) : (
                        ordersList.map(order => (
                          <tr key={order.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', fontSize: '14px' }}>
                            <td style={{ padding: '16px', fontFamily: 'monospace', fontWeight: 600 }}>{order.order_id}</td>
                            <td style={{ padding: '16px' }}>{order.customer_name}</td>
                            <td style={{ padding: '16px', color: 'var(--text-secondary)' }}>{new Date(order.order_date).toLocaleDateString()}</td>
                            <td style={{ padding: '16px' }}>₹{(order.total_amount / 1.05).toFixed(2)}</td>
                            <td style={{ padding: '16px', color: 'var(--text-secondary)' }}>₹{(order.total_amount - (order.total_amount / 1.05)).toFixed(2)}</td>
                            <td style={{ padding: '16px', fontWeight: 600, color: 'var(--accent-color, #d4af37)' }}>₹{parseFloat(order.total_amount).toLocaleString('en-IN')}</td>
                            <td style={{ padding: '16px' }}>
                              <span className={`order-row-badge ${order.payment_status === 'Paid' ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
                                {order.payment_status}
                              </span>
                            </td>
                            <td style={{ padding: '16px' }}>
                              <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => {
                                setConfirmedOrder(order);
                                setShowInvoiceModal(true);
                              }}>
                                <FileText size={12} /> View Invoice
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {/* 7. ANALYTICS TAB */}
            {dashboardTab === 'analytics' && (() => {
              const paidRevenue = ordersList.filter(o => o.payment_status === 'Paid').reduce((sum, o) => sum + parseFloat(o.total_amount), 0);
              const totalBilling = ordersList.reduce((sum, o) => sum + parseFloat(o.total_amount), 0);
              const pendingBill = totalBilling - paidRevenue;
              const aov = ordersList.length > 0 ? (totalBilling / ordersList.length) : 0;

              const garmentDist = {};
              customersList.forEach(c => {
                if (c.garment_type) garmentDist[c.garment_type] = (garmentDist[c.garment_type] || 0) + 1;
              });

              const necklineDist = {};
              const sleeveDist = {};
              customersList.forEach(c => {
                if (c.neckline_style) necklineDist[c.neckline_style] = (necklineDist[c.neckline_style] || 0) + 1;
                if (c.sleeve_style) sleeveDist[c.sleeve_style] = (sleeveDist[c.sleeve_style] || 0) + 1;
              });

              const topGarmentsList = Object.entries(garmentDist).sort((a, b) => b[1] - a[1]).slice(0, 4);
              const topNecklinesList = Object.entries(necklineDist).sort((a, b) => b[1] - a[1]).slice(0, 4);
              const topSleevesList = Object.entries(sleeveDist).sort((a, b) => b[1] - a[1]).slice(0, 4);

              const busyTailors = tailors.filter(t => t.status === 'Busy').length;
              const avgTailorRating = tailors.length > 0 ? (tailors.reduce((sum, t) => sum + parseFloat(t.rating), 0) / tailors.length) : 5.0;

              return (
                <>
                  <header className="portal-header">
                    <div className="portal-header-left">
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                          Business Analytics & Trends
                        </h1>
                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Summary of revenues, style preferences, and operations workload.</p>
                      </div>
                    </div>
                    <div className="portal-header-right">
                      <div className="user-profile-widget">
                        <div className="user-avatar-circle">
                          <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                        </div>
                        <span>Hi, {currentUser.first_name}</span>
                      </div>
                    </div>
                  </header>

                  <div className="analytics-metrics-grid" style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                    gap: '24px',
                    marginTop: '24px'
                  }}>
                    {/* Revenue Card */}
                    <div className="metric-panel-card" style={{
                      background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                      border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                      borderRadius: '12px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Collected Revenue</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: 'var(--accent-color, #d4af37)' }}>
                        ₹{paidRevenue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>From paid customer orders</span>
                    </div>

                    {/* Pending Bills Card */}
                    <div className="metric-panel-card" style={{
                      background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                      border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                      borderRadius: '12px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Pending Invoices</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: '#ffc107' }}>
                        ₹{pendingBill.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Awaiting full or partial payment</span>
                    </div>

                    {/* Average Order Value Card */}
                    <div className="metric-panel-card" style={{
                      background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                      border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                      borderRadius: '12px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Average Ticket Size</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: '#4a90e2' }}>
                        ₹{aov.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Per bespoke order</span>
                    </div>

                    {/* Total Registered Clients */}
                    <div className="metric-panel-card" style={{
                      background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                      border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                      borderRadius: '12px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Client Base</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: '#2ec4b6' }}>
                        {customersList.length} Clients
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Total boutique directory profiles</span>
                    </div>
                  </div>

                  {/* Operational and Trend Columns */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px', marginTop: '32px' }}>
                    
                    {/* Left side: Styles & Design Trends */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      <div className="analytics-card-section" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Popular Garment Types</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          {topGarmentsList.map(([garment, count], idx) => {
                            const pct = Math.round((count / customersList.length) * 100) || 0;
                            return (
                              <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                <div style={{ display: 'flex', justifycontent: 'space-between', fontSize: '13px' }}>
                                  <span>{garment}</span>
                                  <span style={{ fontWeight: 600 }}>{count} ({pct}%)</span>
                                </div>
                                <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                                  <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent-color, #d4af37)', borderRadius: '3px' }}></div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      <div className="analytics-card-section" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Neckline & Sleeve Trends</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                          <div>
                            <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase' }}>Top Necklines</h4>
                            {topNecklinesList.map(([style, count], idx) => (
                              <div key={idx} style={{ fontSize: '13px', display: 'flex', justifycontent: 'space-between', padding: '4px 0' }}>
                                <span>{style}</span>
                                <span style={{ fontWeight: 600 }}>{count}</span>
                              </div>
                            ))}
                          </div>
                          <div>
                            <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase' }}>Top Sleeves</h4>
                            {topSleevesList.map(([style, count], idx) => (
                              <div key={idx} style={{ fontSize: '13px', display: 'flex', justifycontent: 'space-between', padding: '4px 0' }}>
                                <span>{style}</span>
                                <span style={{ fontWeight: 600 }}>{count}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Right side: Staff & Internal Metrics */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      <div className="analytics-card-section" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Staff & Workload Overview</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', fontSize: '14px' }}>
                          <div style={{ display: 'flex', justifycontent: 'space-between', alignItems: 'center' }}>
                            <span>Total Tailoring Team</span>
                            <span style={{ fontWeight: 600 }}>{tailors.length} Tailors</span>
                          </div>
                          <div style={{ display: 'flex', justifycontent: 'space-between', alignItems: 'center' }}>
                            <span>Busy / Assigned Tailors</span>
                            <span style={{ fontWeight: 600, color: '#ffc107' }}>{busyTailors} Busy</span>
                          </div>
                          <div style={{ display: 'flex', justifycontent: 'space-between', alignItems: 'center' }}>
                            <span>Available Staff capacity</span>
                            <span style={{ fontWeight: 600, color: '#2ec4b6' }}>{tailors.length - busyTailors} Free</span>
                          </div>
                          <div style={{ display: 'flex', justifycontent: 'space-between', alignItems: 'center' }}>
                            <span>Atelier Average Rating</span>
                            <span style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                              ⭐ {avgTailorRating.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="analytics-card-section" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Order Status Breakdown</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          {Object.entries(dashboardData?.stats?.status_distribution || {}).map(([status, count], idx) => {
                            const pct = Math.round((count / ordersList.length) * 100) || 0;
                            return (
                              <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                <div style={{ display: 'flex', justifycontent: 'space-between', fontSize: '13px' }}>
                                  <span>{status}</span>
                                  <span style={{ fontWeight: 600 }}>{count} ({pct}%)</span>
                                </div>
                                <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                                  <div style={{ width: `${pct}%`, height: '100%', background: '#4a90e2', borderRadius: '3px' }}></div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>

                  </div>
                </>
              );
            })()}

            {/* 8. MY ACCOUNT SETTINGS TAB */}
            {dashboardTab === 'account' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        My Account Settings
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Manage your boutique profile and atelier details.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
                    </div>
                  </div>
                </header>

                <div className="account-settings-container" style={{ marginTop: '24px', display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '32px' }}>
                  {/* Left profile summary */}
                  <div className="content-card" style={{ alignItems: 'center', textAlign: 'center', gap: '16px' }}>
                    <div className="profile-large-avatar" style={{
                      width: '120px',
                      height: '120px',
                      borderRadius: '50%',
                      overflow: 'hidden',
                      border: '3px solid var(--accent-color, #d4af37)'
                    }}>
                      <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=200" alt="Profile" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    </div>
                    <div>
                      <h3 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>{currentUser.first_name} {currentUser.last_name}</h3>
                      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>Boutique Owner</p>
                    </div>
                    
                    <div style={{ width: '100%', height: '1px', background: 'var(--border-color, rgba(255,255,255,0.08))' }}></div>
                    
                    <div style={{ alignSelf: 'stretch', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
                      <div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', textTransform: 'uppercase' }}>Tenant Domain</div>
                        <div style={{ fontWeight: 600, color: 'var(--accent-color, #d4af37)' }}>
                          {localStorage.getItem('tenant_id') || 'Aditi\'s Boutique'}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', textTransform: 'uppercase' }}>Atelier Email</div>
                        <div style={{ fontWeight: 600 }}>{currentUser.email}</div>
                      </div>
                      <div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', textTransform: 'uppercase' }}>Registered Since</div>
                        <div style={{ fontWeight: 600 }}>June 2024</div>
                      </div>
                    </div>
                  </div>

                  {/* Right editable profile settings */}
                  <div className="content-card">
                    <h3 className="card-title">Edit Profile Information</h3>
                    <form style={{ display: 'flex', flexDirection: 'column', gap: '20px' }} onSubmit={(e) => { e.preventDefault(); alert("Profile updated successfully!"); }}>
                      <div className="form-grid-2">
                        <div className="form-group">
                          <label className="form-label">First Name</label>
                          <input 
                            type="text" 
                            className="form-control" 
                            defaultValue={currentUser.first_name} 
                            required
                          />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Last Name</label>
                          <input 
                            type="text" 
                            className="form-control" 
                            defaultValue={currentUser.last_name} 
                            required
                          />
                        </div>
                      </div>

                      <div className="form-group">
                        <label className="form-label">Email Address</label>
                        <input 
                          type="email" 
                          className="form-control" 
                          defaultValue={currentUser.email} 
                          disabled 
                          style={{ opacity: 0.6, cursor: 'not-allowed' }}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Boutique Name</label>
                        <input 
                          type="text" 
                          className="form-control" 
                          defaultValue={`${currentUser.first_name}'s Atelier`} 
                          required
                        />
                      </div>

                      <button type="submit" className="btn-primary" style={{ alignSelf: 'flex-start', marginTop: '8px' }}>
                        Save Changes
                      </button>
                    </form>
                  </div>
                </div>
              </>
            )}
          </main>

          {/* Fabrics CRUD Modal Overlay */}
          {showFabricModal && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '500px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    {editingFabric ? 'Edit Fabric Details' : 'Add New Fabric to Catalog'}
                  </h3>
                  <button className="close-btn" onClick={() => setShowFabricModal(false)}><X size={20} /></button>
                </div>
                
                <form onSubmit={handleSaveFabric} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Fabric Name</label>
                    <input 
                      type="text" 
                      required 
                      className="form-control" 
                      placeholder="e.g. Chanderi Silk" 
                      value={fabricForm.name}
                      onChange={e => setFabricForm({...fabricForm, name: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Material</label>
                      <input 
                        type="text" 
                        required 
                        className="form-control" 
                        placeholder="e.g. Silk Blend" 
                        value={fabricForm.material}
                        onChange={e => setFabricForm({...fabricForm, material: e.target.value})}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Color</label>
                      <input 
                        type="text" 
                        required 
                        className="form-control" 
                        placeholder="e.g. Aqua Blue" 
                        value={fabricForm.color}
                        onChange={e => setFabricForm({...fabricForm, color: e.target.value})}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Price per Meter (₹)</label>
                    <input 
                      type="number" 
                      required 
                      min="0"
                      step="0.01"
                      className="form-control" 
                      placeholder="e.g. 1250" 
                      value={fabricForm.price_per_meter}
                      onChange={e => setFabricForm({...fabricForm, price_per_meter: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Image URL (Optional)</label>
                    <input 
                      type="url" 
                      className="form-control" 
                      placeholder="e.g. https://images.unsplash.com/photo-..." 
                      value={fabricForm.image_url}
                      onChange={e => setFabricForm({...fabricForm, image_url: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '4px 0' }}>
                    <input 
                      type="checkbox" 
                      id="fabricAvailable"
                      checked={fabricForm.is_available}
                      onChange={e => setFabricForm({...fabricForm, is_available: e.target.checked})}
                    />
                    <label htmlFor="fabricAvailable" style={{ fontSize: '13px', cursor: 'pointer' }}>Available in Inventory</label>
                  </div>

                  <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowFabricModal(false)}>Cancel</button>
                    <button type="submit" className="btn-primary">Save Fabric</button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Tailors CRUD Modal Overlay */}
          {showTailorModal && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '500px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    {editingTailor ? 'Edit Tailor Details' : 'Add New Tailor Profile'}
                  </h3>
                  <button className="close-btn" onClick={() => setShowTailorModal(false)}><X size={20} /></button>
                </div>
                
                <form onSubmit={handleSaveTailor} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Tailor Name</label>
                    <input 
                      type="text" 
                      required 
                      className="form-control" 
                      placeholder="e.g. Master Shabbir" 
                      value={tailorForm.name}
                      onChange={e => setTailorForm({...tailorForm, name: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Specialty</label>
                    <input 
                      type="text" 
                      required 
                      className="form-control" 
                      placeholder="e.g. Lehenga Specialist, Gowns" 
                      value={tailorForm.specialty}
                      onChange={e => setTailorForm({...tailorForm, specialty: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Rating (1.0 — 5.0)</label>
                      <input 
                        type="number" 
                        required 
                        min="1"
                        max="5"
                        step="0.1"
                        className="form-control" 
                        placeholder="5.0" 
                        value={tailorForm.rating}
                        onChange={e => setTailorForm({...tailorForm, rating: e.target.value})}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Status</label>
                      <select 
                        className="form-control"
                        value={tailorForm.status}
                        onChange={e => setTailorForm({...tailorForm, status: e.target.value})}
                      >
                        <option value="Available">Available</option>
                        <option value="Busy">Busy</option>
                      </select>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowTailorModal(false)}>Cancel</button>
                    <button type="submit" className="btn-primary">Save Tailor</button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Designs CRUD Modal Overlay */}
          {showDesignModal && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '500px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    {editingDesign ? 'Edit Design Details' : 'Add New Design to Collection'}
                  </h3>
                  <button className="close-btn" onClick={() => setShowDesignModal(false)}><X size={20} /></button>
                </div>
                
                <form onSubmit={handleSaveDesign} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Design Name</label>
                    <input 
                      type="text" 
                      required 
                      className="form-control" 
                      placeholder="e.g. Royal Maroon Velvet Lehenga" 
                      value={designForm.name}
                      onChange={e => setDesignForm({...designForm, name: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Garment Category</label>
                      <select 
                        className="form-control"
                        value={designForm.garment_type}
                        onChange={e => setDesignForm({...designForm, garment_type: e.target.value})}
                      >
                        <option value="Lehenga">Lehenga</option>
                        <option value="Gown">Gown</option>
                        <option value="Saree">Saree</option>
                        <option value="Kurti">Kurti</option>
                        <option value="Sherwani">Sherwani</option>
                        <option value="Anarkali">Anarkali</option>
                      </select>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Design Type</label>
                      <select 
                        className="form-control"
                        value={designForm.is_boutique}
                        onChange={e => setDesignForm({...designForm, is_boutique: e.target.value === 'true' || e.target.value === true})}
                      >
                        <option value="true">Boutique Catalog Collection</option>
                        <option value="false">AI Suggestion Template</option>
                      </select>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Neckline Style (Optional)</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. Sweetheart Neck" 
                        value={designForm.neckline_style}
                        onChange={e => setDesignForm({...designForm, neckline_style: e.target.value})}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Sleeve Style (Optional)</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. Cap Sleeve" 
                        value={designForm.sleeve_style}
                        onChange={e => setDesignForm({...designForm, sleeve_style: e.target.value})}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Catalog Price (₹) - Only for Boutique Catalog</label>
                    <input 
                      type="number" 
                      min="0"
                      step="0.01"
                      className="form-control" 
                      placeholder="e.g. 45000" 
                      value={designForm.price}
                      onChange={e => setDesignForm({...designForm, price: e.target.value})}
                      disabled={designForm.is_boutique === false || designForm.is_boutique === 'false'}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Image URL (Optional)</label>
                    <input 
                      type="url" 
                      className="form-control" 
                      placeholder="e.g. https://images.unsplash.com/photo-..." 
                      value={designForm.image_url}
                      onChange={e => setDesignForm({...designForm, image_url: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Description (Optional)</label>
                    <textarea 
                      className="form-control" 
                      placeholder="e.g. Hand-embroidered with gold thread, georgette base..." 
                      rows="3"
                      value={designForm.description}
                      onChange={e => setDesignForm({...designForm, description: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowDesignModal(false)}>Cancel</button>
                    <button type="submit" className="btn-primary">Save Design</button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 5. ORDER TYPE SELECTOR (Image 5) */}
      {view === 'order-selector' && (
        <div className="portal-layout">
          {/* Reuse Sidebar for Portal Continuity */}
          <aside className="portal-sidebar">
            <div className="portal-sidebar-logo">TRYON2BUY</div>
            <div className="portal-sidebar-logo-sub">THE ATELIER EXPERIENCE</div>
            
            <nav className="portal-menu">
              <a className="portal-menu-item" onClick={() => setView('dashboard')}><Users size={16} /> Dashboard</a>
              <a className="portal-menu-item"><ShoppingBag size={16} /> My Orders</a>
              <a className="portal-menu-item"><Calendar size={16} /> Appointments</a>
              <a className="portal-menu-item"><Scissors size={16} /> Measurements</a>
              <a className="portal-menu-item" onClick={handleLogout}><User size={16} /> Logout</a>
            </nav>
          </aside>

          <main className="portal-main">
            <div className="selector-container">
              <div className="selector-header">
                <h1 className="selector-title" style={{ fontFamily: 'var(--font-serif)', fontSize: '32px' }}>Create New Custom Order</h1>
                <p className="selector-subtitle" style={{ color: 'var(--text-secondary)' }}>Choose how you would like to initiate this bespoke order creation.</p>
              </div>

              <div className="selector-cards-grid">
                {/* Option 1: Existing Customer */}
                <div className="selector-option-card" onClick={openExistingCustomerModal}>
                  <div className="selector-option-icon">
                    <Users size={32} />
                  </div>
                  <h3 className="selector-option-title">Existing Customer</h3>
                  <p className="selector-option-desc">Select a client profile from your database and retrieve their measurements.</p>
                  
                  <div className="selector-features-list">
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Use saved measurements</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>View past orders & prefs</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Faster order creation</span>
                    </div>
                  </div>

                  <button className="selector-card-btn">
                    Select Existing Customer
                    <ArrowRight size={14} />
                  </button>
                </div>

                {/* Option 2: New Customer */}
                <div className="selector-option-card" onClick={handleStartNewCustomer}>
                  <div className="selector-option-icon">
                    <User size={32} />
                  </div>
                  <h3 className="selector-option-title">New Customer</h3>
                  <p className="selector-option-desc">Create a new customer profile and input their measurements from scratch.</p>

                  <div className="selector-features-list">
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Add customer details</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Capture measurements</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Start custom journey</span>
                    </div>
                  </div>

                  <button className="selector-card-btn">
                    Create New Customer
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>

              {/* Explanatory Flow Diagrams at the bottom */}
              <div className="selector-flow-explain-box">
                <h4 className="selector-flow-explain-title">How the creation process works</h4>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
                  {/* Flow with Existing Customer */}
                  <div>
                    <h5 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '16px' }}>FLOW WITH EXISTING CUSTOMER:</h5>
                    <div className="flow-steps-visual">
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><Users size={16} /></div>
                        <span className="flow-step-node-title">Select Customer</span>
                        <span className="flow-step-node-desc">Search and select client from database</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><FileText size={16} /></div>
                        <span className="flow-step-node-title">Review Profile</span>
                        <span className="flow-step-node-desc">Check sizes and preferences</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><Sparkles size={16} /></div>
                        <span className="flow-step-node-title">Create Order</span>
                        <span className="flow-step-node-desc">Define styles, fabrics and details</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><Check size={16} /></div>
                        <span className="flow-step-node-title">Proceed to Journey</span>
                        <span className="flow-step-node-desc">Stitching and fitting commences</span>
                      </div>
                    </div>
                  </div>

                  {/* Flow with New Customer */}
                  <div>
                    <h5 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '16px' }}>FLOW WITH NEW CUSTOMER:</h5>
                    <div className="flow-steps-visual">
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><User size={16} /></div>
                        <span className="flow-step-node-title">Add Personal Details</span>
                        <span className="flow-step-node-desc">Input names and contact credentials</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><Scissors size={16} /></div>
                        <span className="flow-step-node-title">Capture Sizes</span>
                        <span className="flow-step-node-desc">Log exact body dimensions</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><Compass size={16} /></div>
                        <span className="flow-step-node-title">Style Preferences</span>
                        <span className="flow-step-node-desc">Choose fabrics, cuts, necklines</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><ArrowRight size={16} /></div>
                        <span className="flow-step-node-title">Proceed to Journey</span>
                        <span className="flow-step-node-desc">Submit for creation workflow</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </main>



          {/* Existing Customer Search Modal Overlay */}
          {showSearchModal && (
            <div className="existing-customer-search-modal">
              <div className="search-modal-card">
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Select Existing Customer</h3>
                  <button className="close-btn" onClick={() => setShowSearchModal(false)}><X size={20} /></button>
                </div>
                
                <div className="search-input-wrapper" style={{ width: '100%' }}>
                  <Search size={18} />
                  <input 
                    type="text" 
                    placeholder="Search by customer name or mobile number..." 
                    value={searchModalQuery}
                    onChange={(e) => setSearchModalQuery(e.target.value)}
                    className="form-control"
                    autoFocus
                  />
                </div>

                <div className="search-results-list">
                  {filteredSearchModalCustomers.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '13px' }}>
                      No customers found matching "{searchModalQuery}"
                    </div>
                  ) : (
                    filteredSearchModalCustomers.map(cust => (
                      <div 
                        key={cust.id} 
                        className="search-result-item"
                        onClick={() => handleSelectExistingCustomer(cust)}
                      >
                        <div>
                          <div className="search-result-name">{cust.first_name} {cust.last_name}</div>
                          <div className="search-result-phone">📞 {cust.mobile_number}</div>
                        </div>
                        <span className="search-result-garment">{cust.garment_type}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 6. 5-STEP CREATION WIZARD FLOW */}
      {view === 'wizard' && (
        <div className="wizard-outer-wrapper" style={{ display: 'flex', flexDirection: 'column', width: '100%', minHeight: '100vh', backgroundColor: '#fcfcfd' }}>
          {/* Brand header & stepper */}
          <div className="wizard-header-container" style={{ borderBottom: '1px solid var(--border-color)', backgroundColor: '#fff', padding: '16px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', maxWidth: '1280px', margin: '0 auto 16px' }}>
              <div className="brand-logo" style={{ fontSize: '20px', fontWeight: 800, letterSpacing: '1px', color: 'var(--text-primary)' }}>TRYON2BUY</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <HelpCircle size={16} /> Need help?
                </span>
                <span style={{ cursor: 'pointer', color: 'var(--text-secondary)' }} onClick={() => setView('dashboard')}>
                  <X size={20} />
                </span>
              </div>
            </div>
            
            {/* Stepper progress bar */}
            <div className="stepper-progress-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', maxWidth: '1000px', margin: '0 auto', position: 'relative' }}>
              {[
                { number: 1, label: 'Personal details', sub: 'Completed' },
                { number: 2, label: 'Measurements', sub: 'Completed' },
                { number: 3, label: 'Design Discovery', sub: 'Style preferences' },
                { number: 4, label: 'Fabric Selection', sub: 'Choose fabrics' },
                { number: 5, label: 'Tailor Assignment', sub: 'Assign tailor' },
                { number: 6, label: 'Complete & Create Order', sub: 'review & confirm' }
              ].map((step, index) => {
                const stepNum = index + 1;
                const isCompleted = currentStep > stepNum;
                const isActive = currentStep === stepNum;
                return (
                  <React.Fragment key={step.number}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', flex: 1, position: 'relative', zIndex: 2 }}>
                      <div style={{
                        width: '28px',
                        height: '28px',
                        borderRadius: '50%',
                        backgroundColor: isCompleted ? '#107c41' : (isActive ? '#0f291e' : '#f1f3f5'),
                        color: isCompleted || isActive ? '#fff' : 'var(--text-secondary)',
                        border: isActive ? '2px solid #107c41' : 'none',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '12px',
                        fontWeight: 600,
                        marginBottom: '8px'
                      }}>
                        {isCompleted ? <Check size={14} /> : step.number}
                      </div>
                      <span style={{ fontSize: '11px', fontWeight: isActive || isCompleted ? 600 : 500, color: isActive || isCompleted ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                        {step.label}
                      </span>
                      <span style={{ fontSize: '9px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        {isActive ? 'review & confirm' : (isCompleted ? 'Completed' : step.sub)}
                      </span>
                    </div>
                    {index < 5 && (
                      <div style={{
                        height: '2px',
                        flex: 1,
                        backgroundColor: currentStep > stepNum ? '#107c41' : '#e0e0e0',
                        margin: '0 -20px',
                        transform: 'translateY(-20px)',
                        zIndex: 1
                      }}></div>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
          <div className="main-content" style={{ padding: '40px 24px 100px', maxWidth: '1280px', margin: '0 auto', width: '100%' }}>
            <div className="workspace-panel">
            {/* STEP 1: Personal Details */}
            {currentStep === 1 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Create Customer</h1>
                  <p className="page-subtitle">Onboard new clients into the TryOn2Buy ecosystem. Capture style preferences and measurements for a personalized atelier experience.</p>
                </div>

                <div className="content-card">
                  <div className="card-title">
                    <Users size={20} />
                    Customer Profile
                  </div>

                  <div className="profile-upload-widget">
                    <div className="photo-preview-placeholder" onClick={() => document.getElementById('profile-picker').click()}>
                      {profilePhotoPreview ? (
                        <img src={profilePhotoPreview} alt="Preview" />
                      ) : (
                        <Upload size={24} />
                      )}
                    </div>
                    <div className="photo-upload-actions">
                      <label className="upload-btn-label">
                        Upload Photo
                        <input 
                          type="file" 
                          id="profile-picker" 
                          accept="image/*" 
                          style={{ display: 'none' }} 
                          onChange={handleProfilePhotoChange}
                        />
                      </label>
                      <span className="upload-btn-sub">JPG, PNG up to 5MB</span>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">First Name <span className="required">*</span></label>
                      <input 
                        type="text" 
                        value={customerForm.first_name}
                        onChange={(e) => setCustomerForm({...customerForm, first_name: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. Amara"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Last Name <span className="required">*</span></label>
                      <input 
                        type="text" 
                        value={customerForm.last_name}
                        onChange={(e) => setCustomerForm({...customerForm, last_name: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. Singh"
                      />
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">Mobile Number <span className="required">*</span></label>
                      <div className="input-wrapper">
                        <span className="input-icon-left" style={{ fontSize: '14px', left: '12px' }}>🇮🇳 +91</span>
                        <input 
                          type="tel" 
                          value={customerForm.mobile_number}
                          onChange={(e) => setCustomerForm({...customerForm, mobile_number: e.target.value})}
                          style={{ paddingLeft: '65px' }}
                          placeholder="98765 43210"
                        />
                      </div>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Email Address</label>
                      <input 
                        type="email" 
                        value={customerForm.email_address || ''}
                        onChange={(e) => setCustomerForm({...customerForm, email_address: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. amara.s@example.com"
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Address <span className="required">*</span></label>
                    <input 
                      type="text" 
                      value={customerForm.address || ''}
                      onChange={(e) => setCustomerForm({...customerForm, address: e.target.value})}
                      className="form-control" 
                      placeholder="Street name, Apartment, City, State, PIN code"
                    />
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">City / Region <span className="required">*</span></label>
                      <input 
                        type="text" 
                        value={customerForm.city_region || ''}
                        onChange={(e) => setCustomerForm({...customerForm, city_region: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. New Delhi"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Source <span className="required">*</span></label>
                      <select 
                        value={customerForm.source}
                        onChange={(e) => setCustomerForm({...customerForm, source: e.target.value})}
                        className="form-control"
                      >
                        <option value="Walk In">Walk In</option>
                        <option value="Instagram">Instagram</option>
                        <option value="Referral">Referral</option>
                        <option value="Website">Website</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">Customer Type <span className="required">*</span></label>
                      <select 
                        value={customerForm.customer_type}
                        onChange={(e) => setCustomerForm({...customerForm, customer_type: e.target.value})}
                        className="form-control"
                      >
                        <option value="Women">Women</option>
                        <option value="Men">Men</option>
                        <option value="Kids">Kids</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Garment Type <span className="required">*</span></label>
                      <select 
                        value={customerForm.garment_type}
                        onChange={(e) => setCustomerForm({...customerForm, garment_type: e.target.value})}
                        className="form-control"
                      >
                        <option value="Lehenga">Lehenga</option>
                        <option value="Gown">Gown</option>
                        <option value="Saree">Saree</option>
                        <option value="Anarkali">Anarkali</option>
                        <option value="Suit">Suit</option>
                        <option value="Kurti">Kurti</option>
                        <option value="Sherwani">Sherwani</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">Neckline</label>
                      <select 
                        value={customerForm.neckline_style || ''}
                        onChange={(e) => setCustomerForm({...customerForm, neckline_style: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Neckline Type</option>
                        <option value="V-Neck">V-Neck</option>
                        <option value="Round Neck">Round Neck</option>
                        <option value="Boat Neck">Boat Neck</option>
                        <option value="Collar">Collar</option>
                        <option value="Sweetheart">Sweetheart</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Sleeve Style</label>
                      <select 
                        value={customerForm.sleeve_style || ''}
                        onChange={(e) => setCustomerForm({...customerForm, sleeve_style: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Sleeve Type</option>
                        <option value="Full Sleeve">Full Sleeve</option>
                        <option value="Half Sleeve">Half Sleeve</option>
                        <option value="Sleeveless">Sleeveless</option>
                        <option value="Cap Sleeve">Cap Sleeve</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">Back Style</label>
                      <select 
                        value={customerForm.back_style || ''}
                        onChange={(e) => setCustomerForm({...customerForm, back_style: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Back Style</option>
                        <option value="Deep U">Deep U</option>
                        <option value="Keyhole">Keyhole</option>
                        <option value="Backless">Backless</option>
                        <option value="Standard">Standard</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Length</label>
                      <select 
                        value={customerForm.length_preference || ''}
                        onChange={(e) => setCustomerForm({...customerForm, length_preference: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Length</option>
                        <option value="Floor Length">Floor Length</option>
                        <option value="Ankle Length">Ankle Length</option>
                        <option value="Knee Length">Knee Length</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">Silhouette</label>
                      <select 
                        value={customerForm.silhouette || ''}
                        onChange={(e) => setCustomerForm({...customerForm, silhouette: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Silhouette Type</option>
                        <option value="A-Line">A-Line</option>
                        <option value="Straight Fit">Straight Fit</option>
                        <option value="Flared">Flared</option>
                        <option value="Mermaid">Mermaid</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Embellishments</label>
                      <select 
                        value={customerForm.embellishments || ''}
                        onChange={(e) => setCustomerForm({...customerForm, embellishments: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Embellishments</option>
                        <option value="Zari Work">Zari Work</option>
                        <option value="Sequin Embroidery">Sequin Embroidery</option>
                        <option value="Beadwork">Beadwork</option>
                        <option value="Minimal Lace">Minimal Lace</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">Pattern Style</label>
                      <select 
                        value={customerForm.pattern_style || ''}
                        onChange={(e) => setCustomerForm({...customerForm, pattern_style: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Pattern Style</option>
                        <option value="Floral Prints">Floral Prints</option>
                        <option value="Traditional Brocade">Traditional Brocade</option>
                        <option value="Solid Plain">Solid Plain</option>
                        <option value="Geometrical">Geometrical</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Occasion</label>
                      <select 
                        value={customerForm.occasion || ''}
                        onChange={(e) => setCustomerForm({...customerForm, occasion: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Occasion</option>
                        <option value="Wedding / Bridal">Wedding / Bridal</option>
                        <option value="Festive wear">Festive wear</option>
                        <option value="Formal Event">Formal Event</option>
                        <option value="Casual wear">Casual wear</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Custom Requirements</label>
                    <textarea 
                      value={customerForm.custom_requirements || ''}
                      onChange={(e) => setCustomerForm({...customerForm, custom_requirements: e.target.value})}
                      className="form-control"
                      placeholder="Specify custom preferences (e.g. padding, side zippers, extra margin)"
                    />
                  </div>
                </div>

                {/* Additional Information Card */}
                <div className="content-card">
                  <div className="card-title">
                    <FolderOpen size={20} />
                    Additional Information
                  </div>

                  <div className="form-grid-3">
                    <div className="form-group">
                      <label className="form-label">Date of Birth</label>
                      <input 
                        type="date" 
                        value={customerForm.date_of_birth || ''}
                        onChange={(e) => setCustomerForm({...customerForm, date_of_birth: e.target.value})}
                        className="form-control"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Occupation</label>
                      <input 
                        type="text" 
                        value={customerForm.occupation || ''}
                        onChange={(e) => setCustomerForm({...customerForm, occupation: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. Entrepreneur"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Preferred Communication</label>
                      <select 
                        value={customerForm.preferred_communication}
                        onChange={(e) => setCustomerForm({...customerForm, preferred_communication: e.target.value})}
                        className="form-control"
                      >
                        <option value="WhatsApp">WhatsApp</option>
                        <option value="Call">Phone Call</option>
                        <option value="Email">Email</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Notes</label>
                    <textarea 
                      value={customerForm.notes || ''}
                      onChange={(e) => setCustomerForm({...customerForm, notes: e.target.value})}
                      className="form-control"
                      placeholder="Any additional notes about the customer..."
                    />
                  </div>
                </div>
              </>
            )}

            {/* STEP 2: Measurements */}
            {currentStep === 2 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Measurements</h1>
                  <p className="page-subtitle">Record precision measurements for bespoke tailoring. Accurate specifications are stored securely in the client profile.</p>
                </div>

                <div className="content-card">
                  <div className="card-title">
                    <Scissors size={20} />
                    Body Specifications (inches)
                  </div>

                  <div className="form-grid-2">
                    {Object.keys(customerForm.measurements || {}).map(field => (
                      <div className="form-group" key={field}>
                        <label className="form-label" style={{ textTransform: 'capitalize' }}>
                          {field.replace('_', ' ')} (in)
                        </label>
                        <input 
                          type="number" 
                          step="0.25"
                          value={customerForm.measurements?.[field] || ''}
                          onChange={(e) => {
                            const newMeasurements = {...(customerForm.measurements || {}), [field]: e.target.value};
                            setCustomerForm({...customerForm, measurements: newMeasurements});
                          }}
                          className="form-control" 
                          placeholder="0.00"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* STEP 3: Design Discovery */}
            {currentStep === 3 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Design Preferences</h1>
                  <p className="page-subtitle">Help us understand your style. Share references or explore ideas from our AI and curated collections to create a look that's uniquely yours.</p>
                </div>

                <div className="content-card">
                  {/* Three-tab Source Selector Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '20px' }}>
                    <div 
                      className={`quick-action-item ${designSourceTab === 'references' ? 'active-border' : ''}`}
                      onClick={() => setDesignSourceTab('references')}
                      style={{ 
                        flexDirection: 'row', 
                        alignItems: 'center', 
                        justifyContent: 'flex-start',
                        textAlign: 'left', 
                        padding: '16px',
                        cursor: 'pointer',
                        borderColor: designSourceTab === 'references' ? 'var(--text-primary)' : 'var(--border-color)',
                        backgroundColor: designSourceTab === 'references' ? '#fafbfc' : '#fff'
                      }}
                    >
                      <div className="quick-action-icon-box" style={{ width: '32px', height: '32px', flexShrink: 0 }}>
                        <Upload size={14} />
                      </div>
                      <div style={{ marginLeft: '12px' }}>
                        <h4 style={{ fontSize: '13px', fontWeight: 600 }}>My References</h4>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Share your design inspiration</p>
                      </div>
                    </div>

                    <div 
                      className={`quick-action-item ${designSourceTab === 'ai' ? 'active-border' : ''}`}
                      onClick={() => setDesignSourceTab('ai')}
                      style={{ 
                        flexDirection: 'row', 
                        alignItems: 'center', 
                        justifyContent: 'flex-start',
                        textAlign: 'left', 
                        padding: '16px',
                        cursor: 'pointer',
                        borderColor: designSourceTab === 'ai' ? 'var(--text-primary)' : 'var(--border-color)',
                        backgroundColor: designSourceTab === 'ai' ? '#fafbfc' : '#fff'
                      }}
                    >
                      <div className="quick-action-icon-box" style={{ width: '32px', height: '32px', flexShrink: 0 }}>
                        <Sparkles size={14} />
                      </div>
                      <div style={{ marginLeft: '12px' }}>
                        <h4 style={{ fontSize: '13px', fontWeight: 600 }}>AI Suggestions</h4>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Get ideas curated for you</p>
                      </div>
                    </div>

                    <div 
                      className={`quick-action-item ${designSourceTab === 'catalog' ? 'active-border' : ''}`}
                      onClick={() => setDesignSourceTab('catalog')}
                      style={{ 
                        flexDirection: 'row', 
                        alignItems: 'center', 
                        justifyContent: 'flex-start',
                        textAlign: 'left', 
                        padding: '16px',
                        cursor: 'pointer',
                        borderColor: designSourceTab === 'catalog' ? 'var(--text-primary)' : 'var(--border-color)',
                        backgroundColor: designSourceTab === 'catalog' ? '#fafbfc' : '#fff'
                      }}
                    >
                      <div className="quick-action-icon-box" style={{ width: '32px', height: '32px', flexShrink: 0 }}>
                        <FolderOpen size={14} />
                      </div>
                      <div style={{ marginLeft: '12px' }}>
                        <h4 style={{ fontSize: '13px', fontWeight: 600 }}>Boutique Catalog</h4>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Explore our collections</p>
                      </div>
                    </div>
                  </div>

                  {/* Multi-source banner */}
                  <div className="accent-banner" style={{ margin: '4px 0 12px', backgroundColor: '#fdf6ed', borderColor: '#fbeedb', color: '#c08030', justifyContent: 'center' }}>
                    <Sparkles size={14} />
                    <span>You can select one or more sources</span>
                  </div>

                  {/* Tab contents */}
                  {designSourceTab === 'references' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      <div className="card-title">
                        <Upload size={18} />
                        Share Your Design References
                      </div>
                      <div className="drag-drop-zone" onClick={() => document.getElementById('design-picker').click()}>
                        <div className="drag-drop-icon">
                          <Upload size={24} />
                        </div>
                        <div className="drag-drop-text">Drag & drop images here or <span>Upload Images</span></div>
                        <div className="drag-drop-subtext">JPG, PNG up to 10MB each • You can upload up to 10 images</div>
                        <input 
                          type="file" 
                          id="design-picker" 
                          multiple 
                          accept="image/*" 
                          style={{ display: 'none' }} 
                          onChange={handleDesignFilesChange}
                        />
                      </div>

                      {designPreviews.length > 0 && (
                        <div className="uploaded-references-section">
                          <div className="section-subtitle">Your Uploaded References ({designPreviews.length}/10)</div>
                          <div className="references-grid">
                            {designPreviews.map((src, i) => (
                              <div className="reference-image-card" key={i}>
                                <img src={src} alt={`Ref ${i+1}`} />
                                <button className="remove-image-btn" onClick={() => {
                                  setDesignPreviews(prev => prev.filter((_, idx) => idx !== i));
                                  setDesignFiles(prev => prev.filter((_, idx) => idx !== i));
                                }}>×</button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {designsLoading ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '48px 24px' }}>
                      <div style={{
                        width: '32px',
                        height: '32px',
                        border: '3px solid #f3f3f3',
                        borderTop: '3px solid var(--accent-color, #c08030)',
                        borderRadius: '50%',
                        animation: 'spin 1s linear infinite',
                        marginBottom: '16px'
                      }}></div>
                      <style>{`
                        @keyframes spin {
                          0% { transform: rotate(0deg); }
                          100% { transform: rotate(360deg); }
                        }
                      `}</style>
                      <div style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)' }}>Personalizing design recommendations...</div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>Querying templates matching your {customerForm.garment_type} preferences</div>
                    </div>
                  ) : (
                    <>
                      {designSourceTab === 'ai' && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                          <div className="card-title">
                            <Sparkles size={18} />
                            AI Suggestions Curated For You
                          </div>
                          
                          {aiSuggestions.length === 0 ? (
                            <div style={{ padding: '32px 16px', textAlign: 'center', border: '1px dashed var(--border-color)', borderRadius: '8px', color: 'var(--text-secondary)' }}>
                              <Sparkles size={24} style={{ marginBottom: '8px', color: 'var(--text-secondary)' }} />
                              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>No suggestions matching style criteria</div>
                              <div style={{ fontSize: '11px', marginTop: '2px' }}>Try uploading your own references or updating measurements style selections.</div>
                            </div>
                          ) : (
                            <div className="fabrics-grid">
                              {aiSuggestions.map((item, idx) => {
                                const isSeedImage = item.image_url.startsWith('design_');
                                const resolvedImg = isSeedImage ? `http://localhost:8000/media/${item.image_url}` : item.image_url;
                                const isSelected = selectedDesignTemplates.includes(resolvedImg);
                                return (
                                  <div 
                                    key={idx}
                                    className={`fabric-card ${isSelected ? 'selected' : ''}`}
                                    onClick={() => {
                                      if (isSelected) {
                                        setSelectedDesignTemplates(prev => prev.filter(u => u !== resolvedImg));
                                      } else {
                                        setSelectedDesignTemplates(prev => [...prev, resolvedImg]);
                                      }
                                    }}
                                  >
                                    <div className="fabric-image-container">
                                      <img src={resolvedImg} alt={item.name} />
                                      {isSelected && (
                                        <div className="fabric-badge">
                                          <Check size={14} />
                                        </div>
                                      )}
                                    </div>
                                    <div className="fabric-details">
                                      <span className="fabric-title">{item.name}</span>
                                      {item.description && (
                                        <span className="fabric-subtitle" style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px', display: 'block' }}>
                                          {item.description}
                                        </span>
                                      )}
                                      {item.neckline_style === customerForm.neckline_style && customerForm.neckline_style && (
                                        <span style={{ display: 'inline-block', fontSize: '9px', backgroundColor: '#e2f5ec', color: '#107c41', padding: '2px 6px', borderRadius: '99px', marginTop: '6px', fontWeight: 500 }}>
                                          Matched {item.neckline_style}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      )}

                      {designSourceTab === 'catalog' && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                          <div className="card-title">
                            <FolderOpen size={18} />
                            Explore Boutique Collections
                          </div>
                          
                          {boutiqueDesigns.length === 0 ? (
                            <div style={{ padding: '32px 16px', textAlign: 'center', border: '1px dashed var(--border-color)', borderRadius: '8px', color: 'var(--text-secondary)' }}>
                              <FolderOpen size={24} style={{ marginBottom: '8px', color: 'var(--text-secondary)' }} />
                              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>No boutique designs available</div>
                              <div style={{ fontSize: '11px', marginTop: '2px' }}>There are currently no catalog designs in stock for this garment type ({customerForm.garment_type}).</div>
                            </div>
                          ) : (
                            <div className="fabrics-grid">
                              {boutiqueDesigns.map((item, idx) => {
                                const isSeedImage = item.image_url.startsWith('design_');
                                const resolvedImg = isSeedImage ? `http://localhost:8000/media/${item.image_url}` : item.image_url;
                                const isSelected = selectedDesignTemplates.includes(resolvedImg);
                                return (
                                  <div 
                                    key={idx}
                                    className={`fabric-card ${isSelected ? 'selected' : ''}`}
                                    onClick={() => {
                                      if (isSelected) {
                                        setSelectedDesignTemplates(prev => prev.filter(u => u !== resolvedImg));
                                      } else {
                                        setSelectedDesignTemplates(prev => [...prev, resolvedImg]);
                                      }
                                    }}
                                  >
                                    <div className="fabric-image-container">
                                      <img src={resolvedImg} alt={item.name} />
                                      {isSelected && (
                                        <div className="fabric-badge">
                                          <Check size={14} />
                                        </div>
                                      )}
                                    </div>
                                    <div className="fabric-details">
                                      <span className="fabric-title">{item.name}</span>
                                      <span className="fabric-price" style={{ fontWeight: 600, display: 'block', margin: '4px 0', fontSize: '12px', color: 'var(--text-primary)' }}>
                                        ₹{parseFloat(item.price).toLocaleString('en-IN')}
                                      </span>
                                      {item.description && (
                                        <span className="fabric-subtitle" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>
                                          {item.description}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}

                  <div className="form-group">
                    <label className="form-label">Add Notes (Optional)</label>
                    <textarea 
                      value={designNotes}
                      onChange={(e) => setDesignNotes(e.target.value)}
                      className="form-control"
                      placeholder="Tell us what you like about these designs... e.g. color, fit, neckline, embroidery, overall vibe"
                    />
                  </div>
                </div>
              </>
            )}

            {/* STEP 4: Fabric Selection */}
            {currentStep === 4 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Fabric Selection</h1>
                  <p className="page-subtitle">Choose the perfect fabric that brings the design to life. Browse from your uploaded fabrics or explore premium boutique inventory.</p>
                </div>

                <div className="content-card">
                  <div className="tabs-header">
                    <button 
                      className={`tab-btn ${fabricTab === 'boutique' ? 'active' : ''}`}
                      onClick={() => setFabricTab('boutique')}
                    >
                      Boutique Fabrics
                    </button>
                    <button 
                      className={`tab-btn ${fabricTab === 'my-fabric' ? 'active' : ''}`}
                      onClick={() => setFabricTab('my-fabric')}
                    >
                      Customer Fabrics (My Fabrics)
                    </button>
                  </div>

                  {fabricTab === 'my-fabric' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      <div className="drag-drop-zone" onClick={() => document.getElementById('fabric-picker').click()}>
                        <div className="drag-drop-icon">
                          <Upload size={24} />
                        </div>
                        <div className="drag-drop-text">Upload Fabric Images</div>
                        <div className="drag-drop-subtext">Upload clear, well-lit photos for accurate representation</div>
                        <input 
                          type="file" 
                          id="fabric-picker" 
                          multiple 
                          accept="image/*" 
                          style={{ display: 'none' }} 
                          onChange={handleFabricFilesChange}
                        />
                      </div>

                      {fabricPreviews.length > 0 && (
                        <div className="uploaded-references-section">
                          <div className="section-subtitle">Uploaded Fabrics ({fabricPreviews.length}/10)</div>
                          <div className="references-grid">
                            {fabricPreviews.map((src, i) => (
                              <div className="reference-image-card" key={i}>
                                <img src={src} alt={`Fabric ${i+1}`} />
                                <button className="remove-image-btn" onClick={() => {
                                  setFabricPreviews(prev => prev.filter((_, idx) => idx !== i));
                                  setFabricFiles(prev => prev.filter((_, idx) => idx !== i));
                                }}>×</button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div>
                      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', overflowX: 'auto' }}>
                        {['All', 'Pure Silk', 'Zari Silk', 'Linen', 'Silk', 'Cotton'].map(cat => (
                          <button 
                            key={cat}
                            className={`tab-btn`} 
                            style={{ 
                              padding: '6px 12px', 
                              fontSize: '12px',
                              borderRadius: '99px',
                              border: '1px solid var(--border-color)',
                              background: fabricFilter === cat ? 'var(--text-primary)' : '#fff',
                              color: fabricFilter === cat ? '#fff' : 'var(--text-secondary)'
                            }}
                            onClick={() => setFabricFilter(cat)}
                          >
                            {cat}
                          </button>
                        ))}
                      </div>

                      <div className="fabrics-grid">
                        {fabrics
                          .filter(f => fabricFilter === 'All' || f.material === fabricFilter)
                          .map(f => {
                            const isSeedImage = f.image_url.startsWith('fabric_');
                            const resolvedImg = isSeedImage ? `http://localhost:8000/media/${f.image_url}` : f.image_url;
                            return (
                              <div 
                                key={f.id} 
                                className={`fabric-card ${selectedFabric?.id === f.id ? 'selected' : ''}`}
                                onClick={() => setSelectedFabric(f)}
                              >
                                <div className="fabric-image-container">
                                  <img src={resolvedImg} alt={f.name} onError={(e) => {
                                    e.target.src = 'https://images.unsplash.com/photo-1574169208507-84376144848b?w=400';
                                  }} />
                                  {selectedFabric?.id === f.id && (
                                    <div className="fabric-badge">
                                      <Check size={14} />
                                    </div>
                                  )}
                                </div>
                                <div className="fabric-details">
                                  <span className="fabric-title">{f.name} - {f.color}</span>
                                  <span className="fabric-price">₹{f.price_per_meter.toLocaleString('en-IN')} / mtr</span>
                                </div>
                              </div>
                            );
                          })}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* STEP 5: Tailor Assignment & Pricing Review */}
            {currentStep === 5 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Review & Assignment</h1>
                  <p className="page-subtitle">Assign a master tailor to craft the creation and review the itemized cost breakdown before finalizing the order.</p>
                </div>

                <div className="content-card">
                  <div className="card-title">
                    <Scissors size={20} />
                    Assign Master Tailor
                  </div>

                  <div className="tailors-list">
                    {tailors.map(t => (
                      <div 
                        key={t.id} 
                        className={`tailor-row ${selectedTailor?.id === t.id ? 'selected' : ''}`}
                        onClick={() => setSelectedTailor(t)}
                        style={{ display: 'flex', gap: '16px', alignItems: 'center' }}
                      >
                        <div style={{ width: '40px', height: '40px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0 }}>
                          <img src={getTailorAvatarUrl(t.name)} alt={t.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        </div>
                        <div className="tailor-info" style={{ flex: 1 }}>
                          <div className="tailor-name-row">
                            <span className="tailor-name">{t.name}</span>
                            <span className={`tailor-status-tag ${t.status.toLowerCase()}`}>
                              {t.status}
                            </span>
                          </div>
                          <span className="tailor-spec">{t.specialty}</span>
                        </div>
                        <div className="tailor-rating">
                          <Star size={14} />
                          {parseFloat(t.rating).toFixed(1)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* STEP 6: Review & Complete Order / Payment */}
            {currentStep === 6 && (
              <>
                {!paymentPhase ? (
                  // Review & Complete Order Phase (Mockup 1)
                  <>
                    <div className="page-title-group">
                      <h1 className="page-title">Review & Complete Order</h1>
                      <p className="page-subtitle">Almost there! Please review your selections and order details. Once confirmed, we'll hand it over to your tailor and keep you updated at every step.</p>
                    </div>

                    <div className="accent-banner" style={{ margin: '4px 0 16px', backgroundColor: '#e2f5ec', borderColor: '#c3ebdb', color: '#107c41', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Check size={16} />
                      <span>All set! You're ready to create your order.</span>
                    </div>

                    {/* Section 1: Order Summary */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <FileText size={20} />
                          1. Order Summary
                        </div>
                        <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setCurrentStep(3)}>
                          Edit
                        </button>
                      </div>

                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          {selectedDesignTemplates.length > 0 ? (
                            <img src={selectedDesignTemplates[0]} alt="Garment" style={{ width: '48px', height: '48px', borderRadius: '6px', objectFit: 'cover', border: '1px solid var(--border-color)' }} />
                          ) : designPreviews.length > 0 ? (
                            <img src={designPreviews[0]} alt="Garment" style={{ width: '48px', height: '48px', borderRadius: '6px', objectFit: 'cover', border: '1px solid var(--border-color)' }} />
                          ) : (
                            <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ShoppingBag size={20} /></div>
                          )}
                          <div>
                            <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>GARMENT</span>
                            <span style={{ fontSize: '13px', fontWeight: 600 }}>{customerForm.customer_type} • {customerForm.garment_type}</span>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          {fabricTab === 'boutique' && selectedFabric ? (
                            <>
                              <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#f1f3f5', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
                                <img src={selectedFabric.image_url ? (selectedFabric.image_url.startsWith('fabric_') ? `http://localhost:8000/media/${selectedFabric.image_url}` : selectedFabric.image_url) : ''} alt="Fabric" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                              </div>
                              <div>
                                <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>FABRIC</span>
                                <span style={{ fontSize: '13px', fontWeight: 600 }}>{selectedFabric.name}</span>
                              </div>
                            </>
                          ) : fabricPreviews.length > 0 ? (
                            <>
                              <div style={{ width: '48px', height: '48px', borderRadius: '6px', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
                                <img src={fabricPreviews[0]} alt="Fabric" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                              </div>
                              <div>
                                <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>FABRIC</span>
                                <span style={{ fontSize: '13px', fontWeight: 600 }}>Uploaded Fabric</span>
                              </div>
                            </>
                          ) : (
                            <>
                              <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--border-color)' }}><Upload size={20} /></div>
                              <div>
                                <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>FABRIC</span>
                                <span style={{ fontSize: '13px', fontWeight: 600 }}>Customer Fabric</span>
                              </div>
                            </>
                          )}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div style={{ width: '32px', height: '32px', borderRadius: '50%', border: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <span style={{ width: '20px', height: '20px', borderRadius: '50%', backgroundColor: getColorCircleStyle(selectedFabric?.color || 'Custom') }}></span>
                          </div>
                          <div>
                            <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>COLOR</span>
                            <span style={{ fontSize: '13px', fontWeight: 600 }}>{selectedFabric ? selectedFabric.color : 'Custom'}</span>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#0f291e', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>
                            <Sparkles size={20} />
                          </div>
                          <div>
                            <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>WORK/EMBROIDERY</span>
                            <span style={{ fontSize: '13px', fontWeight: 600 }}>{customerForm.embellishments || 'Zari & Thread'}</span>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div>
                            <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>OCCASION</span>
                            <span style={{ fontSize: '13px', fontWeight: 600 }}>{customerForm.occasion || 'Wedding'}</span>
                          </div>
                        </div>
                      </div>

                      {(customerForm.neckline_style || customerForm.sleeve_style || customerForm.back_style || customerForm.silhouette || customerForm.pattern_style) && (
                        <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px dashed var(--border-color)' }}>
                          <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', fontWeight: 600, textTransform: 'uppercase', marginBottom: '8px' }}>Style Specifications</span>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '12px' }}>
                            {customerForm.neckline_style && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Neckline</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.neckline_style}</span>
                              </div>
                            )}
                            {customerForm.sleeve_style && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Sleeves</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.sleeve_style}</span>
                              </div>
                            )}
                            {customerForm.back_style && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Back Style</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.back_style}</span>
                              </div>
                            )}
                            {customerForm.silhouette && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Silhouette</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.silhouette}</span>
                              </div>
                            )}
                            {customerForm.pattern_style && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Pattern</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.pattern_style}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Section 2: Measurements */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <Scissors size={20} />
                          2. Measurements
                        </div>
                        <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setCurrentStep(2)}>
                          Edit
                        </button>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '20px', backgroundColor: '#fcfdfd', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                        <div style={{ width: '40px', height: '40px', borderRadius: '50%', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><User size={20} /></div>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '13px', fontWeight: 600 }}>Default Set</span>
                            <span style={{ fontSize: '9px', backgroundColor: '#fbeedb', color: '#c08030', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>Primary</span>
                          </div>
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Body Specifications (inches)</span>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <span style={{ fontSize: '14px', fontWeight: 700, display: 'block' }}>
                            {Object.keys(customerForm.measurements || {}).filter(k => k !== 'additional_measurements' && customerForm.measurements?.[k]).length || 10}
                          </span>
                          <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Measurements</span>
                        </div>
                        <div style={{ width: '1px', height: '32px', backgroundColor: 'var(--border-color)' }}></div>
                        <div style={{ textAlign: 'right' }}>
                          <span style={{ fontSize: '14px', fontWeight: 700, display: 'block' }}>98%</span>
                          <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Accuracy Score</span>
                        </div>
                        <div style={{ width: '1px', height: '32px', backgroundColor: 'var(--border-color)' }}></div>
                        <div style={{ textAlign: 'right' }}>
                          <span style={{ fontSize: '12px', fontWeight: 600, display: 'block' }}>
                            {new Date().toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
                          </span>
                          <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Measured On</span>
                        </div>
                      </div>
                    </div>

                    {/* Section 3: Tailor Details */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <User size={20} />
                          3. Tailor Details
                        </div>
                        <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setCurrentStep(5)}>
                          Edit
                        </button>
                      </div>

                      {selectedTailor ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '20px', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                          <div style={{ width: '48px', height: '48px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0 }}>
                            <img src={getTailorAvatarUrl(selectedTailor.name)} alt={selectedTailor.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          </div>
                          <div style={{ flex: 1 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ fontSize: '15px', fontWeight: 600 }}>{selectedTailor.name}</span>
                              <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#107c41', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '8px' }}><Check size={8} /></span>
                            </div>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block' }}>{selectedTailor.specialty} • 12+ Years Experience</span>
                            <div style={{ display: 'flex', gap: '6px', marginTop: '6px', flexWrap: 'wrap' }}>
                              {getTailorTags(selectedTailor.name).map((tag, idx) => (
                                <span key={idx} style={{ fontSize: '9px', backgroundColor: '#f1f3f5', padding: '2px 6px', borderRadius: '4px', color: 'var(--text-secondary)' }}>{tag}</span>
                              ))}
                              <span style={{ fontSize: '9px', backgroundColor: '#f1f3f5', padding: '2px 6px', borderRadius: '4px', color: 'var(--text-secondary)' }}>+2</span>
                            </div>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <span style={{ fontSize: '13px', fontWeight: 700, display: 'block' }}>98%</span>
                            <span style={{ fontSize: '9px', color: 'var(--text-secondary)' }}>ON-TIME DELIVERY</span>
                          </div>
                          <div style={{ width: '1px', height: '32px', backgroundColor: 'var(--border-color)' }}></div>
                          <div style={{ textAlign: 'right' }}>
                            <span style={{ fontSize: '13px', fontWeight: 700, display: 'block' }}>1200+</span>
                            <span style={{ fontSize: '9px', color: 'var(--text-secondary)' }}>ORDERS DONE</span>
                          </div>
                          <div style={{ width: '1px', height: '32px', backgroundColor: 'var(--border-color)' }}></div>
                          <div style={{ textAlign: 'right' }}>
                            <span style={{ fontSize: '13px', fontWeight: 700, display: 'block' }}>5 km</span>
                            <span style={{ fontSize: '9px', color: 'var(--text-secondary)' }}>FROM BOUTIQUE</span>
                          </div>
                        </div>
                      ) : (
                        <div style={{ padding: '16px', textAlign: 'center', border: '1px dashed var(--border-color)', borderRadius: '8px', color: 'var(--text-secondary)' }}>
                          No tailor assigned. Go back to Step 5 to assign a tailor.
                        </div>
                      )}
                    </div>

                    {/* Section 4: Delivery Details */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <ShoppingBag size={20} />
                          4. Delivery Details
                        </div>
                        <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setCurrentStep(1)}>
                          Edit
                        </button>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
                        <div>
                          <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block', fontWeight: 600, textTransform: 'uppercase', marginBottom: '6px' }}>DELIVERY ADDRESS</span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <MapPin size={16} style={{ color: 'var(--text-secondary)', flexShrink: 0, marginTop: '2px' }} />
                            <div>
                              <span style={{ fontSize: '12px', fontWeight: 600, display: 'block' }}>{customerForm.first_name} {customerForm.last_name}</span>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', lineHeight: 1.4 }}>{customerForm.address || 'B-32, Green Park Extension, New Delhi - 110016, India'}</span>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginTop: '4px' }}>📞 +91 {customerForm.mobile_number}</span>
                            </div>
                          </div>
                        </div>

                        <div>
                          <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block', fontWeight: 600, textTransform: 'uppercase', marginBottom: '6px' }}>DELIVERY METHOD</span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <ShoppingBag size={16} style={{ color: 'var(--text-secondary)', flexShrink: 0, marginTop: '2px' }} />
                            <div>
                              <span style={{ fontSize: '12px', fontWeight: 600, display: 'block' }}>Standard Delivery</span>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>Estimated delivery by</span>
                              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginTop: '2px' }}>
                                {new Date(Date.now() + 15 * 24 * 60 * 60 * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div>
                          <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block', fontWeight: 600, textTransform: 'uppercase', marginBottom: '6px' }}>COMMUNICATION</span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <MessageSquare size={16} style={{ color: '#107c41', flexShrink: 0, marginTop: '2px' }} />
                            <div>
                              <span style={{ fontSize: '12px', fontWeight: 600, display: 'block' }}>WhatsApp</span>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>+91 {customerForm.mobile_number}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Section 5: Special Instructions */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <MessageSquare size={20} />
                          Add Special Instructions (Optional)
                        </div>
                        <Edit2 size={16} style={{ color: 'var(--text-secondary)' }} />
                      </div>
                      <textarea
                        value={specialInstructions}
                        onChange={(e) => setSpecialInstructions(e.target.value)}
                        className="form-control"
                        placeholder="e.g. Prefer hand embroidery on dupatta, avoid bright colors, etc."
                        style={{ minHeight: '80px', fontSize: '12px' }}
                      />
                    </div>

                    {/* Step 6 Review Buttons */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '20px' }}>
                      <button className="btn-secondary" onClick={handleBack}>
                        <ArrowLeft size={16} /> Back: Tailor Assignment
                      </button>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <button className="btn-secondary" onClick={handleSaveDraft}>
                          Save as Draft
                        </button>
                        <button className="btn-primary" onClick={handleNext}>
                          Create Order & Pay <ArrowRight size={16} />
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  // Create Order & Continue / Payment Options Phase (Mockup 2)
                  <>
                    <div className="page-title-group">
                      <h1 className="page-title">Create Order & Continue</h1>
                      <p className="page-subtitle">You're all set! Choose how you'd like to proceed with your payment. Pay now in full or pay partially and the remaining after design completion.</p>
                    </div>

                    <div className="accent-banner" style={{ margin: '4px 0 16px', backgroundColor: '#e2f5ec', borderColor: '#c3ebdb', color: '#107c41', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <ShieldCheck size={16} />
                      <span>Your order is safe and secure with TryOn2Buy.</span>
                    </div>

                    {/* Order Review Summary Row */}
                    <div className="content-card">
                      <h3 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '16px' }}>1. Order Review</h3>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', alignItems: 'center', gap: '20px' }}>
                        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
                          {selectedDesignTemplates.length > 0 ? (
                            <img src={selectedDesignTemplates[0]} alt="Garment" style={{ width: '48px', height: '48px', borderRadius: '6px', objectFit: 'cover' }} />
                          ) : designPreviews.length > 0 ? (
                            <img src={designPreviews[0]} alt="Garment" style={{ width: '48px', height: '48px', borderRadius: '6px', objectFit: 'cover' }} />
                          ) : (
                            <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ShoppingBag size={20} /></div>
                          )}
                          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Garment</span>
                              <span style={{ fontSize: '12px', fontWeight: 600 }}>{customerForm.customer_type} • {customerForm.garment_type}</span>
                            </div>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Fabric</span>
                              <span style={{ fontSize: '12px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                {fabricTab === 'boutique' && selectedFabric ? (
                                  <>
                                    {selectedFabric.name}
                                    <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: getColorCircleStyle(selectedFabric.color), display: 'inline-block' }}></span>
                                    {selectedFabric.color}
                                  </>
                                ) : fabricPreviews.length > 0 ? (
                                  'Uploaded Fabric'
                                ) : (
                                  'Customer Fabric'
                                )}
                              </span>
                            </div>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Work / Embroidery</span>
                              <span style={{ fontSize: '12px', fontWeight: 600 }}>{customerForm.embellishments || 'Zari & Thread'}</span>
                            </div>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Tailor</span>
                              <span style={{ fontSize: '12px', fontWeight: 600 }}>{selectedTailor?.name || 'Rohit Mehra'}</span>
                            </div>
                          </div>
                        </div>

                        <button className="btn-secondary" style={{ fontSize: '11px', padding: '6px 12px' }} onClick={() => setPaymentPhase(false)}>
                          View Full Summary
                        </button>
                      </div>
                    </div>

                    {/* Payment Options Section */}
                    <div className="content-card">
                      <h3 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '16px' }}>2. Payment Options</h3>
                      <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '16px' }}>Choose how you want to pay for your order.</p>

                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        {/* Option 1: Full Payment */}
                        <div 
                          onClick={() => setPaymentOption('full')}
                          style={{
                            border: `2px solid ${paymentOption === 'full' ? '#0f291e' : 'var(--border-color)'}`,
                            borderRadius: '8px',
                            padding: '20px',
                            cursor: 'pointer',
                            backgroundColor: paymentOption === 'full' ? '#fcfdfd' : '#fff',
                            position: 'relative'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                            <div>
                              <span style={{ fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
                                Pay Now (Full Payment)
                                <span style={{ fontSize: '9px', backgroundColor: '#e2f5ec', color: '#107c41', padding: '2px 6px', borderRadius: '4px' }}>Recommended</span>
                              </span>
                              <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '4px' }}>Pay the full amount now and we'll start your design & creation immediately.</p>
                            </div>
                            <div style={{ width: '16px', height: '16px', borderRadius: '50%', border: '2px solid #0f291e', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              {paymentOption === 'full' && <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#0f291e' }}></div>}
                            </div>
                          </div>
                          
                          <span style={{ fontSize: '20px', fontWeight: 800, display: 'block', color: 'var(--text-primary)', marginBottom: '16px' }}>
                            ₹{getTotalPrice().toLocaleString('en-IN')}
                          </span>

                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                              <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#e2f5ec', color: '#107c41', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px' }}><Check size={8} /></span>
                              Priority design & production
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                              <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#e2f5ec', color: '#107c41', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px' }}><Check size={8} /></span>
                              Faster delivery
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                              <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#e2f5ec', color: '#107c41', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px' }}><Check size={8} /></span>
                              Full peace of mind
                            </div>
                          </div>
                        </div>

                        {/* Option 2: Partial Payment */}
                        <div 
                          onClick={() => setPaymentOption('partial')}
                          style={{
                            border: `2px solid ${paymentOption === 'partial' ? '#0f291e' : 'var(--border-color)'}`,
                            borderRadius: '8px',
                            padding: '20px',
                            cursor: 'pointer',
                            backgroundColor: paymentOption === 'partial' ? '#fcfdfd' : '#fff',
                            position: 'relative'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                            <div>
                              <span style={{ fontSize: '13px', fontWeight: 700 }}>Pay Partially Now</span>
                              <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '4px' }}>Pay a part now to confirm your order. Pay the remaining after design is completed.</p>
                            </div>
                            <div style={{ width: '16px', height: '16px', borderRadius: '50%', border: '2px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              {paymentOption === 'partial' && <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#0f291e' }}></div>}
                            </div>
                          </div>

                          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px', marginBottom: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <div>
                                <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Pay Now (50%)</span>
                                <span style={{ fontSize: '16px', fontWeight: 700 }}>₹{(getTotalPrice() / 2).toLocaleString('en-IN')}</span>
                              </div>
                              <span style={{ fontSize: '8px', backgroundColor: '#f1f3f5', color: 'var(--text-secondary)', padding: '2px 4px', borderRadius: '2px' }}>Non-refundable</span>
                            </div>
                          </div>

                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Pay After Design Completion</span>
                              <span style={{ fontSize: '16px', fontWeight: 700 }}>₹{(getTotalPrice() / 2).toLocaleString('en-IN')}</span>
                            </div>
                            <span style={{ fontSize: '8px', backgroundColor: '#e2f5ec', color: '#107c41', padding: '2px 4px', borderRadius: '2px', fontWeight: 600 }}>PAY BEFORE PRODUCTION</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* What happens next banner */}
                    <div style={{ display: 'flex', gap: '12px', padding: '16px', backgroundColor: '#fcfdfd', border: '1px solid var(--border-color)', borderRadius: '8px', alignItems: 'center' }}>
                      <Calendar size={20} style={{ color: 'var(--text-secondary)' }} />
                      <div>
                        <h5 style={{ fontSize: '11px', fontWeight: 600 }}>What happens next?</h5>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>We'll create initial design concepts and share with you within 2–3 business days. Once you approve the final design, we'll share the remaining payment link (if applicable) and begin crafting your garment.</p>
                      </div>
                    </div>

                    {/* Terms Checkbox */}
                    <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '10px' }}>
                      <input 
                        type="checkbox" 
                        checked={agreedToTerms} 
                        onChange={(e) => setAgreedToTerms(e.target.checked)}
                        style={{ cursor: 'pointer' }}
                      />
                      <span>I agree to the <span style={{ textDecoration: 'underline' }}>Terms & Conditions</span> and <span style={{ textDecoration: 'underline' }}>Privacy Policy</span>.</span>
                    </label>

                    {/* Step 6 Payment Buttons */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '20px' }}>
                      <button className="btn-secondary" onClick={handleBack}>
                        <ArrowLeft size={16} /> Back: Tailor Assignment
                      </button>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <button className="btn-secondary" onClick={handleSaveDraft}>
                          Save as Draft
                        </button>
                        <button className="btn-primary" onClick={handleNext} disabled={!agreedToTerms} style={{ opacity: agreedToTerms ? 1 : 0.6 }}>
                          Confirm Order & Continue <ArrowRight size={16} />
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </>
            )}
          </div>

          {/* Right Sidebar */}
          <div className="sidebar-panel">
            {currentStep < 5 ? (
              <>
                <div className="sidebar-card">
                  <div className="sidebar-card-title">
                    <Sparkles size={16} />
                    How it works
                  </div>
                  <div className="instruction-steps">
                    <div className="instruction-step">
                      <div className="step-num-badge">1</div>
                      <div className="instruction-step-content">
                        <span className="instruction-step-title">Enter Profile Details</span>
                        <span className="instruction-step-desc">Provide size tags and contact channels.</span>
                      </div>
                    </div>
                    <div className="instruction-step">
                      <div className="step-num-badge">2</div>
                      <div className="instruction-step-content">
                        <span className="instruction-step-title">Submit Measurements</span>
                        <span className="instruction-step-desc">Collect 7 key body specifications.</span>
                      </div>
                    </div>
                    <div className="instruction-step">
                      <div className="step-num-badge">3</div>
                      <div className="instruction-step-content">
                        <span className="instruction-step-title">Bespoke Design & Fabric</span>
                        <span className="instruction-step-desc">Pick reference sketches and fabric rolls.</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="sidebar-card">
                  <div className="sidebar-card-title">
                    <ShieldCheck size={16} />
                    Privacy Assured
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    Customer details, style files, and measurement records are saved exclusively to the TryOn2Buy database cluster and never shared.
                  </p>
                </div>
              </>
            ) : currentStep === 5 ? (
              <div className="sidebar-card">
                <div className="sidebar-card-title">
                  <ShoppingBag size={18} />
                  Order Summary
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px' }}>
                  <div style={{ fontSize: '14px', fontWeight: 600 }}>{customerForm.customer_type} • {customerForm.garment_type}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    Fabric: {fabricTab === 'boutique' && selectedFabric ? `${selectedFabric.name} (${selectedFabric.color})` : 'Customer fabric'}
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div className="summary-item-row">
                    <span>Base Price ({customerForm.garment_type})</span>
                    <span className="price-display">₹{parseFloat(quotePrices.base || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Fabric Charges (3 mtr)</span>
                    <span className="price-display">₹{parseFloat(quotePrices.fabric || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Embroidery & Artisan Work</span>
                    <span className="price-display">₹{parseFloat(quotePrices.embroidery || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Customization Charge</span>
                    <span className="price-display">₹{parseFloat(quotePrices.customization || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Tailoring Charges</span>
                    <span className="price-display">₹{parseFloat(quotePrices.tailoring || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Packaging & Handling</span>
                    <span className="price-display">₹{parseFloat(quotePrices.packaging || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row" style={{ borderTop: '1px solid #f1f3f5', paddingTop: '10px' }}>
                    <span>Subtotal</span>
                    <span className="price-display">₹{getSubtotal().toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Taxes (GST 5%)</span>
                    <span className="price-display">₹{getTaxes().toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row total">
                    <span>Total Amount</span>
                    <span className="price-display total">₹{getTotalPrice().toLocaleString('en-IN')}</span>
                  </div>
                </div>
              </div>
            ) : (
              // Order Summary/Breakdown for Step 6 (Review & Payment)
              <>
                <div className="sidebar-card">
                  <div className="sidebar-card-title">
                    <ShoppingBag size={18} />
                    {paymentPhase ? 'Order Summary' : 'Order Cost Breakdown'}
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px' }}>
                    <div style={{ fontSize: '14px', fontWeight: 600 }}>{customerForm.customer_type} • {customerForm.garment_type}</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      Fabric: {fabricTab === 'boutique' && selectedFabric ? `${selectedFabric.name} (${selectedFabric.color})` : 'Customer fabric'}
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginTop: '16px' }}>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Base Price ({customerForm.garment_type})</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.base || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.base} 
                            onChange={(e) => setQuotePrices({...quotePrices, base: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Fabric ({selectedFabric ? selectedFabric.name : (fabricPreviews.length > 0 ? 'Uploaded Fabric' : 'Customer Fabric')})</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.fabric || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.fabric} 
                            onChange={(e) => setQuotePrices({...quotePrices, fabric: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Embroidery & Work</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.embroidery || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.embroidery} 
                            onChange={(e) => setQuotePrices({...quotePrices, embroidery: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Customization</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.customization || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.customization} 
                            onChange={(e) => setQuotePrices({...quotePrices, customization: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Tailoring Charges</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.tailoring || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.tailoring} 
                            onChange={(e) => setQuotePrices({...quotePrices, tailoring: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Packaging & Handling</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.packaging || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.packaging} 
                            onChange={(e) => setQuotePrices({...quotePrices, packaging: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' }}>
                    <div className="summary-item-row" style={{ fontWeight: 600 }}>
                      <span>Subtotal</span>
                      <span className="price-display">₹{getSubtotal().toLocaleString('en-IN')}</span>
                    </div>
                    <div className="summary-item-row">
                      <span>Taxes (GST 5%)</span>
                      <span className="price-display">₹{getTaxes().toLocaleString('en-IN')}</span>
                    </div>
                    <div className="summary-item-row total" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '12px' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        Total Amount <HelpCircle size={12} style={{ color: 'var(--text-secondary)' }} />
                      </span>
                      <span className="price-display total" style={{ color: '#107c41', fontSize: '20px', fontWeight: 700 }}>
                        ₹{getTotalPrice().toLocaleString('en-IN')}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="sidebar-card" style={{ display: 'flex', gap: '12px', alignItems: 'center', backgroundColor: '#fcfdfd', borderColor: '#e2e8f0' }}>
                  <ShieldCheck size={20} style={{ color: '#107c41', flexShrink: 0 }} />
                  <div>
                    <h5 style={{ fontSize: '12px', fontWeight: 600 }}>Secure Payments</h5>
                    <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>Your payment details are safe with us.</p>
                    <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                      <span style={{ fontSize: '8px', fontWeight: 700, color: '#1a1f36', backgroundColor: '#eaecef', padding: '2px 4px', borderRadius: '2px', letterSpacing: '0.5px' }}>VISA</span>
                      <span style={{ fontSize: '8px', fontWeight: 700, color: '#f79e1b', backgroundColor: '#eaecef', padding: '2px 4px', borderRadius: '2px', letterSpacing: '0.5px' }}>MC</span>
                      <span style={{ fontSize: '8px', fontWeight: 700, color: '#0070d2', backgroundColor: '#eaecef', padding: '2px 4px', borderRadius: '2px', letterSpacing: '0.5px' }}>AMEX</span>
                      <span style={{ fontSize: '8px', fontWeight: 700, color: '#003087', backgroundColor: '#eaecef', padding: '2px 4px', borderRadius: '2px', letterSpacing: '0.5px' }}>RUPAY</span>
                    </div>
                  </div>
                </div>

                {!paymentPhase ? (
                  <div className="sidebar-card">
                    <h5 style={{ fontSize: '13px', fontWeight: 600, marginBottom: '16px' }}>What happens next?</h5>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <div style={{ width: '24px', height: '24px', borderRadius: '4px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><Check size={12} /></div>
                        <div>
                          <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Order Confirmation</h6>
                          <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>You'll receive confirmation on WhatsApp & Email.</p>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <div style={{ width: '24px', height: '24px', borderRadius: '4px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><User size={12} /></div>
                        <div>
                          <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Tailor Notified</h6>
                          <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>We'll share details with {selectedTailor?.name || 'Rohit Mehra'} to start the magic.</p>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <div style={{ width: '24px', height: '24px', borderRadius: '4px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><Scissors size={12} /></div>
                        <div>
                          <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Design & Creation</h6>
                          <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Your garment will be crafted with care and regular updates.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="sidebar-card">
                    <h5 style={{ fontSize: '13px', fontWeight: 600, marginBottom: '16px' }}>Why choose TryOn2Buy?</h5>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div>
                        <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Trusted Tailors</h6>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Verified & experienced professionals</p>
                      </div>
                      <div>
                        <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Premium Quality</h6>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Finest fabrics and craftsmanship</p>
                      </div>
                      <div>
                        <h6 style={{ fontSize: '11px', fontWeight: 600 }}>On-time Delivery</h6>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>We value your time</p>
                      </div>
                      <div>
                        <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Personalized Support</h6>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>We're here for you at every step</p>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
      )}

      {/* CONFIRMED VIEW */}
      {view === 'confirmed' && confirmedOrder && (
        <div className="order-confirmed-container">
          <div className="success-badge-container">
            <div className="success-circle"><Check size={40} /></div>
            <h1 className="success-title">Your Order is Confirmed! 🎉</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '15px' }}>
              Thank you, {customerForm.first_name}! We've received your order and our team has started working on your custom creation.
            </p>
            <div className="order-id-badge">
              <span>Order ID: <strong>{confirmedOrder.order_id}</strong></span>
              <button 
                style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', color: 'var(--text-secondary)' }}
                onClick={() => {
                  navigator.clipboard.writeText(confirmedOrder.order_id);
                  alert("Copied!");
                }}
              >
                <Copy size={14} />
              </button>
            </div>
          </div>

          <div className="order-meta-info-grid">
            <div className="meta-info-block">
              <span className="meta-info-label">Order Date</span>
              <span className="meta-info-val">
                {new Date(confirmedOrder.order_date).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
              </span>
            </div>
            <div className="meta-info-block">
              <span className="meta-info-label">Payment Status</span>
              <span className="meta-info-val" style={{ color: 'var(--success-color)' }}>
                Paid • ₹{confirmedOrder.total_amount.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="meta-info-block">
              <span className="meta-info-label">Estimated Delivery</span>
              <span className="meta-info-val">
                {new Date(confirmedOrder.estimated_delivery).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
              </span>
            </div>
          </div>

          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600 }}>What happens next?</h3>
            <div className="timeline-tracker">
              <div className="timeline-line"></div>
              {[
                { label: 'Stylist Review', desc: 'Your stylist is reviewing your order details.', active: true, completed: true },
                { label: 'Design & Creation', desc: 'Artisans will cut and assemble your custom garment.', active: false, completed: false },
                { label: 'Quality Check', desc: 'Multi-level measurement and stitching validation.', active: false, completed: false },
                { label: 'Packed & Shipped', desc: 'Packed securely and dispatched to your door.', active: false, completed: false }
              ].map((node, i) => (
                <div key={i} className={`timeline-node ${node.completed ? 'completed' : ''} ${node.active ? 'active' : ''}`}>
                  <div className="timeline-node-circle">
                    {node.completed ? <Check size={14} /> : (i + 1)}
                  </div>
                  <span className="timeline-node-label">{node.label}</span>
                  <span className="timeline-node-desc">{node.desc}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="whatsapp-action-card">
            <div className="whatsapp-info">
              <span className="whatsapp-title">Crafting something just for you ✨</span>
              <span className="whatsapp-desc">Need changes or have questions? Chat directly with us on WhatsApp.</span>
            </div>
            <button className="whatsapp-btn" onClick={() => window.open(`https://wa.me/91${customerForm.mobile_number}`)}>
              <MessageSquare size={18} />
              Chat on WhatsApp
            </button>
          </div>

          <div style={{ display: 'flex', gap: '16px', justifyContent: 'center', width: '100%', maxWidth: '450px' }}>
            <button className="btn-secondary" style={{ flex: 1, justifyContent: 'center' }} onClick={() => { setView('dashboard'); fetchDashboardAndConfig(); }}>
              Back to Dashboard
            </button>
            <button className="btn-primary" style={{ flex: 1, justifyContent: 'center', backgroundColor: '#0f291e' }} onClick={() => setShowInvoiceModal(true)}>
              <FileText size={18} /> View & Print Invoice
            </button>
          </div>
        </div>
      )}

      {/* Footer Navigation Bar (Only in Wizard View) */}
      {view === 'wizard' && currentStep < 6 && (
        <div className="footer-actions-bar">
          <div className="footer-left-actions">
            <button className="btn-secondary" onClick={handleBack}>
              <ArrowLeft size={16} />
              Back
            </button>
          </div>
          <div className="footer-right-actions">
            {/* Show Save as Draft only if they are creating a new customer profile (Step 1 or 2) */}
            {currentStep < 3 && (
              <button className="btn-secondary" onClick={handleSaveDraft}>
                Save as Draft
              </button>
            )}
            <button className="btn-primary" onClick={handleNext}>
              {currentStep === 5 ? 'Confirm Order' : 'Next'}
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* INVOICE MODAL */}
      {showInvoiceModal && confirmedOrder && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000,
          padding: '20px'
        }}>
          <div className="invoice-modal-content" style={{
            backgroundColor: '#fff',
            borderRadius: '12px',
            width: '100%',
            maxWidth: '700px',
            maxHeight: '90vh',
            overflowY: 'auto',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
            display: 'flex',
            flexDirection: 'column'
          }}>
            {/* Modal Header */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '16px 24px',
              borderBottom: '1px solid var(--border-color)'
            }} className="no-print">
              <h3 style={{ fontSize: '16px', fontWeight: 700 }}>Customer Invoice</h3>
              <button 
                onClick={() => setShowInvoiceModal(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Invoice Printable Area */}
            <div id="invoice-printable" style={{ padding: '40px', color: '#1a1f36', fontSize: '13px', lineHeight: 1.5 }}>
              {/* Styling for printing */}
              <style>{`
                @media print {
                  body * {
                    visibility: hidden;
                  }
                  #invoice-printable, #invoice-printable * {
                    visibility: visible;
                  }
                  #invoice-printable {
                    position: absolute;
                    left: 0;
                    top: 0;
                    width: 100%;
                    padding: 0;
                  }
                  .no-print {
                    display: none !important;
                  }
                }
              `}</style>

              {/* Invoice Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '32px' }}>
                <div>
                  <h1 style={{ fontSize: '24px', fontWeight: 800, letterSpacing: '1px', color: '#0f291e', margin: 0 }}>TRYON2BUY</h1>
                  <span style={{ fontSize: '10px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '1px' }}>Bespoke Atelier CRM</span>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, textTransform: 'uppercase', color: 'var(--text-secondary)' }}>INVOICE</h2>
                  <span style={{ fontSize: '12px', display: 'block', marginTop: '4px' }}>Invoice ID: <strong>{confirmedOrder.order_id}</strong></span>
                  <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginTop: '2px' }}>
                    Date: {new Date(confirmedOrder.order_date).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
                  </span>
                </div>
              </div>

              {/* Billed To / Designer Details */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '40px', borderTop: '1px solid #eaecef', borderBottom: '1px solid #eaecef', padding: '20px 0', marginBottom: '32px' }}>
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>Billed To:</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, display: 'block' }}>{customerForm.first_name} {customerForm.last_name}</span>
                  <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>{customerForm.address}</span>
                  <span style={{ display: 'block', color: 'var(--text-secondary)' }}>📞 +91 {customerForm.mobile_number}</span>
                  {customerForm.email_address && <span style={{ display: 'block', color: 'var(--text-secondary)' }}>✉️ {customerForm.email_address}</span>}
                </div>
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>Atelier Details:</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, display: 'block' }}>TryOn2Buy Boutique Portal</span>
                  <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>Boutique Owner: {currentUser?.first_name || 'Aditi'} {currentUser?.last_name || 'Mehta'}</span>
                  {selectedTailor && (
                    <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>
                      Assigned Tailor: <strong>{selectedTailor.name}</strong> ({selectedTailor.specialty})
                    </span>
                  )}
                  <span style={{ display: 'block', color: 'var(--text-secondary)' }}>Estimated Delivery: {new Date(confirmedOrder.estimated_delivery).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                </div>
              </div>

              {/* Garment Details Summary */}
              <div style={{ backgroundColor: '#fcfdfd', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px', marginBottom: '32px' }}>
                <h4 style={{ fontSize: '12px', fontWeight: 700, margin: '0 0 12px 0', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Design & Specifications</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', fontSize: '11px' }}>
                  <div>
                    <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Garment Type</span>
                    <strong style={{ fontSize: '12px' }}>{customerForm.customer_type} • {customerForm.garment_type}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Fabric</span>
                    <strong style={{ fontSize: '12px' }}>
                      {fabricTab === 'boutique' && selectedFabric ? `${selectedFabric.name} (${selectedFabric.color})` : 'Customer Fabric'}
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Occasion</span>
                    <strong style={{ fontSize: '12px' }}>{customerForm.occasion || 'Wedding'}</strong>
                  </div>
                  {customerForm.neckline_style && (
                    <div>
                      <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Neckline Style</span>
                      <strong>{customerForm.neckline_style}</strong>
                    </div>
                  )}
                  {customerForm.sleeve_style && (
                    <div>
                      <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Sleeve Style</span>
                      <strong>{customerForm.sleeve_style}</strong>
                    </div>
                  )}
                  {customerForm.back_style && (
                    <div>
                      <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Back Style</span>
                      <strong>{customerForm.back_style}</strong>
                    </div>
                  )}
                </div>
              </div>

              {/* Pricing Table */}
              <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '32px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #eaecef', fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
                    <th style={{ padding: '12px 8px', fontWeight: 600 }}>Description</th>
                    <th style={{ padding: '12px 8px', fontWeight: 600, textAlign: 'right' }}>Amount</th>
                  </tr>
                </thead>
                <tbody style={{ fontSize: '12px' }}>
                  <tr style={{ borderBottom: '1px solid #f1f3f5' }}>
                    <td style={{ padding: '12px 8px' }}>
                      <strong>Base Price ({customerForm.garment_type})</strong>
                      <span style={{ display: 'block', fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>Standard pattern cuts and styling specifications</span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600 }}>₹{parseFloat(confirmedOrder.base_price || 0).toLocaleString('en-IN')}</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f3f5' }}>
                    <td style={{ padding: '12px 8px' }}>
                      <strong>Fabric Charges</strong>
                      <span style={{ display: 'block', fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        {fabricTab === 'boutique' && selectedFabric ? `${selectedFabric.name} - 3 meters` : 'Customer supplied fabric'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600 }}>₹{parseFloat(confirmedOrder.fabric_price || 0).toLocaleString('en-IN')}</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f3f5' }}>
                    <td style={{ padding: '12px 8px' }}>
                      <strong>Embroidery & Artisan Work</strong>
                      <span style={{ display: 'block', fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>Custom thread work, sequence, and detailing</span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600 }}>₹{parseFloat(confirmedOrder.embroidery_price || 0).toLocaleString('en-IN')}</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f3f5' }}>
                    <td style={{ padding: '12px 8px' }}>
                      <strong>Customization Charges</strong>
                      <span style={{ display: 'block', fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>Personal size specifications and alterations</span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600 }}>₹{parseFloat(confirmedOrder.customization_price || 0).toLocaleString('en-IN')}</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f3f5' }}>
                    <td style={{ padding: '12px 8px' }}>
                      <strong>Tailoring Charges</strong>
                      <span style={{ display: 'block', fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>Stitching and pattern matching by {selectedTailor?.name || 'assigned tailor'}</span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600 }}>₹{parseFloat(confirmedOrder.tailoring_charges || 0).toLocaleString('en-IN')}</td>
                  </tr>
                  <tr style={{ borderBottom: '2px solid #eaecef' }}>
                    <td style={{ padding: '12px 8px' }}>
                      <strong>Packaging & Handling</strong>
                      <span style={{ display: 'block', fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>Atelier box packing and shipping validation</span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600 }}>₹{parseFloat(confirmedOrder.packaging_handling || 0).toLocaleString('en-IN')}</td>
                  </tr>
                </tbody>
              </table>

              {/* Subtotal & Taxes Breakdown */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', fontSize: '12px' }}>
                <div style={{ width: '250px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Subtotal</span>
                    <strong style={{ fontWeight: 600 }}>₹{((parseFloat(confirmedOrder.total_amount) || 0) / 1.05).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Taxes (GST 5%)</span>
                    <strong style={{ fontWeight: 600 }}>₹{parseFloat(confirmedOrder.taxes || 0).toLocaleString('en-IN')}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 0 6px 0', borderTop: '2px solid #0f291e', marginTop: '6px', fontSize: '16px' }}>
                    <span style={{ fontWeight: 700, color: '#0f291e' }}>Total Amount</span>
                    <strong style={{ fontWeight: 800, color: '#107c41' }}>₹{parseFloat(confirmedOrder.total_amount || 0).toLocaleString('en-IN')}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '10px', color: 'var(--text-secondary)', borderTop: '1px solid #eaecef', marginTop: '6px' }}>
                    <span>Payment Mode</span>
                    <span>{confirmedOrder.payment_status}</span>
                  </div>
                </div>
              </div>

              {/* Terms Footer */}
              <div style={{ borderTop: '1px solid #eaecef', marginTop: '48px', paddingTop: '20px', textAlign: 'center', fontSize: '10px', color: 'var(--text-secondary)' }}>
                <p style={{ margin: '0 0 4px 0' }}>Thank you for creating your bespoke order with **TRYON2BUY** Atelier.</p>
                <p style={{ margin: 0 }}>This is a computer-generated invoice and does not require a physical signature.</p>
              </div>
            </div>

            {/* Modal Footer Controls */}
            <div style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '12px',
              padding: '16px 24px',
              borderTop: '1px solid var(--border-color)',
              backgroundColor: '#fafbfc',
              borderBottomLeftRadius: '12px',
              borderBottomRightRadius: '12px'
            }} className="no-print">
              <button 
                className="btn-secondary" 
                onClick={() => setShowInvoiceModal(false)}
              >
                Close
              </button>
              <button 
                className="btn-primary" 
                style={{ backgroundColor: '#0f291e' }}
                onClick={() => window.print()}
              >
                Print Invoice
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
