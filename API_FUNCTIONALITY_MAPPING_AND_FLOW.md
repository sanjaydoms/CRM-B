
---


`CRM-B` uses a **schema-per-tenant multi-tenancy model** built on top of Django & Django REST Framework (DRF):
- **Public Schema (`public`)**: Holds global platform tables (`tenants`, `superadmin` logs, `leads`, platform administrators).
- **Tenant Schemas (`schema_name`)**: Each boutique operates in its own isolated database schema containing customers, orders, inventory, catalog, and production data.
- **Middleware Routing (`tenants/middleware.py`)**: 
  - Requests starting with `/api/superadmin/` are automatically pinned to the `public` schema.
  - Tenant API requests starting with `/api/` inspect headers (`X-Tenant-ID`) or domain/subdomain matching to dynamically route database connections to the target tenant's schema before view handlers run.

- **Token Authentication**: Standard DRF Token Authentication (`Authorization: Token <token>`).
- **Isolation Header**: `X-Tenant-ID` header specifies target tenant scope.
- **Role-Based Access Control (`core/roles.py`, `core/permissions.py`)**:
  - `OWNER`: Full boutique owner access.
  - `MASTER`: Production Master tailor, access to garment checklist verification and production stages.
  - `TAILOR`: Artisan/Tailor assigned to specific production tasks.
  - `SUPERVISOR`: Management view for production and staff monitoring.
  - `PLATFORM_ADMIN`: Superadmin access restricted to `/api/superadmin/`.

---


Below is the complete mapping of every API endpoint in CRM-B, detailing its HTTP method, purpose, connected frontend service function, and domain handlers.

---


| Method | Endpoint | Connected Functionality | Frontend API Method (`src/services/api.js`) | Backend Handler / Domain |
|---|---|---|---|---|
| `POST` | `/api/auth/signup/` | Boutique Registration & Owner Account Signup | `api.signup()` | `crm_api.auth_views.SignupView` |
| `POST` | `/api/auth/login/` | User Sign In (issues Auth Token & Tenant ID) | `api.login()` | `crm_api.auth_views.LoginView` |
| `POST` | `/api/auth/logout/` | User Sign Out (invalidates Auth Token) | `api.logout()` | `crm_api.auth_views.LogoutView` |
| `GET` | `/api/auth/me/` | Fetch current user role, profile & tenant info | `api.getMe()` | `crm_api.auth_views.MeView` |
| `POST` | `/api/auth/password-reset/` | Request password reset link via email | `api.requestPasswordReset()` | `crm_api.auth_views.PasswordResetRequestView` |
| `POST` | `/api/auth/password-reset/confirm/` | Confirm password reset with token | `api.confirmPasswordReset()` | `crm_api.auth_views.PasswordResetConfirmView` |
| `POST` | `/api/auth/seed-data/` | Populate tenant with mock testing data | `api.seedMockData()` | `crm_api.auth_views.SeedDataView` |

---


| Method | Endpoint | Connected Functionality | Frontend API Method | Backend Handler / Domain |
|---|---|---|---|---|
| `GET` | `/api/customers/` | List customer directory (summary format) | `api.getCustomers()` | `crm_api.views.CustomerViewSet.list` |
| `POST` | `/api/customers/` | Create customer profile (with photo upload) | `api.createCustomer()` | `crm_api.views.CustomerViewSet.create` |
| `GET` | `/api/customers/{id}/` | Full customer details, orders & history | `api.getCustomer()` | `crm_api.views.CustomerViewSet.retrieve` |
| `PATCH` | `/api/customers/{id}/` | Update customer info & measurements | `api.updateCustomer()` | `crm_api.views.CustomerViewSet.partial_update` |
| `GET` | `/api/customers/{id}/measurement-history/` | View historical measurement edits | N/A | `CustomerViewSet.measurement_history` |
| `POST` | `/api/customers/{id}/design-preferences/` | Save design preferences & inspiration images | `api.saveDesignPreferences()` | `CustomerViewSet.save_design_preferences` |
| `POST` | `/api/customers/{id}/design-preferences/{pref_id}/approve/` | Approve/Sign-off specific design | `api.approveDesign()` | `CustomerViewSet.approve_design_preference` |
| `GET` | `/api/customers/{id}/ai-suggestions/` | Get AI style & fabric recommendations | `api.getAISuggestions()` | `CustomerViewSet.ai_suggestions` |
| `GET` | `/api/customers/{id}/boutique-designs/` | Recommend designs from boutique catalog | `api.getBoutiqueDesigns()` | `CustomerViewSet.boutique_designs` |
| `POST` | `/api/customers/{id}/fabric-selections/` | Save chosen fabric (Boutique or Own fabric) | `api.saveFabricSelection()` | `CustomerViewSet.save_fabric_selection` |
| `POST` | `/api/customers/{id}/create-order/` | Convert consultation into placed Order | `api.createOrder()` | `CustomerViewSet.create_order` |

---


| Method | Endpoint | Connected Functionality | Frontend API Method | Backend Handler / Domain |
|---|---|---|---|---|
| `GET` | `/api/orders/` | List tenant orders (role-scoped) | `api.getOrders()` | `crm_api.views.OrderViewSet.list` |
| `GET` | `/api/orders/{id}/` | Retrieve complete order details & garments | N/A | `crm_api.views.OrderViewSet.retrieve` |
| `PATCH` | `/api/orders/{id}/` | Update order attributes | `api.updateOrder()` | `crm_api.views.OrderViewSet.partial_update` |
| `PATCH` | `/api/orders/{id}/update-status/` | General status update (e.g., In Production) | `api.updateOrderStatus()` | `OrderViewSet.update_status` |
| `POST` | `/api/orders/{id}/assign-stage/` | Assign tailor/artisan to a production stage | `api.assignStage()` | `OrderViewSet.assign_stage` |
| `POST` | `/api/orders/{id}/transition/` | Advance stage with images & notes | `api.transitionStage()` | `OrderViewSet.transition` |
| `PATCH` | `/api/orders/{id}/master-verification/` | Master QC Checklist verification (Master-only) | `api.saveMasterVerification()` | `OrderViewSet.master_verification` |
| `PATCH` | `/api/orders/{id}/submit-completion/` | Final tailor completion submission | `api.submitCompletion()` | `OrderViewSet.submit_completion` |
| `POST` | `/api/orders/{id}/submit-stage-review/` | Supervisor/Master stage review | `api.submitStageReview()` | `OrderViewSet.submit_stage_review` |
| `GET` | `/api/orders/customer-messages/` | Fetch pending WhatsApp customer notifications | `api.getQueuedCustomerMessages()` | `OrderViewSet.customer_messages` |
| `POST` | `/api/orders/{id}/mark-message-sent/` | Mark WhatsApp message sent | `api.markMessageSent()` | `OrderViewSet.mark_message_sent` |
| `POST` | `/api/orders/{id}/garment-images/` | Upload finished garment photo | `api.uploadGarmentImage()` | `OrderViewSet.upload_garment_image` |
| `DELETE` | `/api/orders/{id}/garment-images/{img_id}/` | Delete garment photo | `api.deleteGarmentImage()` | `OrderViewSet.delete_garment_image` |
| `POST` | `/api/orders/{id}/publish-garment-images/` | Publish photos to public tracking page | `api.publishGarmentImages()` | `OrderViewSet.publish_garment_images` |

| Method | Endpoint | Connected Functionality | Frontend API Method | Backend Handler / Domain |
|---|---|---|---|---|
| `GET` | `/api/order-drafts/` | List unplaced order drafts | `api.listOrderDrafts()` | `crm_api.views.OrderDraftViewSet.list` |
| `POST` | `/api/order-drafts/` | Save unplaced order draft | `api.createOrderDraft()` | `crm_api.views.OrderDraftViewSet.create` |
| `GET` | `/api/order-drafts/{id}/` | Open order draft | `api.getOrderDraft()` | `crm_api.views.OrderDraftViewSet.retrieve` |
| `PATCH` | `/api/order-drafts/{id}/` | Save draft edits (optimistic concurrency) | `api.updateOrderDraft()` | `crm_api.views.OrderDraftViewSet.partial_update` |
| `DELETE` | `/api/order-drafts/{id}/` | Discard order draft | `api.deleteOrderDraft()` | `crm_api.views.OrderDraftViewSet.destroy` |
| `POST` | `/api/order-drafts/{id}/confirm/` | Atomic transaction to place final order | `api.confirmOrderDraft()` | `crm_api.views.OrderDraftViewSet.confirm` |

---


| Method | Endpoint | Connected Functionality | Frontend API Method | Backend Handler / Domain |
|---|---|---|---|---|
| `GET` | `/api/production/tasks/` | List active production work items | N/A | `apps.production.views.ProductionTaskViewSet` |
| `GET` | `/api/production/qc/` | View Quality Control inspection logs | N/A | `apps.production.views.QCRecordViewSet` |
| `POST` | `/api/production/qc/` | Create QC inspection record | N/A | `apps.production.views.QCRecordViewSet` |

---


| Method | Endpoint | Connected Functionality | Frontend API Method | Backend Handler / Domain |
|---|---|---|---|---|
| `GET` | `/api/design-studio/context/` | Resolve customer/draft design context | `api.getDesignContext()` | `apps.design_studio.views.DesignContextView` |
| `POST` | `/api/design-studio/discover/` | Search design library & style inspiration | `api.discoverDesigns()` | `apps.design_studio.views.DesignDiscoveryView` |
| `GET` | `/api/design-studio/boards/` | List customer mood boards | `api.getDesignBoards()` | `DesignBoardViewSet.list` |
| `POST` | `/api/design-studio/boards/` | Create customer design mood board | `api.createDesignBoard()` | `DesignBoardViewSet.create` |
| `POST` | `/api/design-studio/boards/{id}/items/` | Add design item to board | `api.addDesignToBoard()` | `DesignBoardViewSet.add_item` |
| `DELETE` | `/api/design-studio/boards/{id}/items/{item_id}/` | Delete item from board | `api.removeDesignFromBoard()` | `DesignBoardViewSet.remove_item` |
| `POST` | `/api/design-studio/boards/{id}/items/{item_id}/select/` | Select design on board | `api.selectBoardDesign()` | `DesignBoardViewSet.select_item` |
| `PATCH` | `/api/design-studio/boards/{id}/items/{item_id}/customise/` | Save design customization notes | `api.customiseBoardDesign()` | `DesignBoardViewSet.customise_item` |
| `PATCH` | `/api/design-studio/boards/{b_id}/items/{i_id}/production-notes/` | Master production notes | `api.saveProductionNotes()` | `DesignBoardViewSet.production_notes` |
| `POST` | `/api/design-studio/boards/{id}/approve/` | Approve entire board | `api.approveDesignBoard()` | `DesignBoardViewSet.approve` |
| `POST` | `/api/design-studio/boards/{id}/save-to-order/` | Link approved board to Order | `api.saveDesignBoardToOrder()` | `DesignBoardViewSet.save_to_order` |
| `GET` | `/api/design-studio/assets/` | Browse design library assets | `api.getDesignLibrary()` | `DesignAssetViewSet.list` |
| `POST` | `/api/design-studio/assets/` | Upload design (with image files) | `api.uploadDesign()` | `DesignAssetViewSet.create` |
| `POST` | `/api/design-studio/assets/{id}/review/` | Master/Owner review design asset | `api.reviewDesign()` | `DesignAssetViewSet.review` |
| `GET` | `/api/design-studio/categories/` | Get design category hierarchy | `api.getDesignCategories()` | `DesignCategoryView` |
| `GET` | `/api/design-studio/dashboard/` | Design Studio overview metrics | `api.getDesignDashboard()` | `DesignDashboardView` |
| `GET` | `/api/design-studio/designers/` | List accredited designers | `api.getDesigners()` | `DesignerViewSet.list` |
| `POST` | `/api/design-studio/designers/` | Create credited designer entry | `api.createDesigner()` | `DesignerViewSet.create` |
| `POST` | `/api/design-studio/designers/{id}/create-login/` | Turn designer into logged-in user | `api.createDesignerLogin()` | `DesignerViewSet.create_login` |
| `GET` | `/api/design-studio/assignments/` | List designer work assignments | `api.getDesignAssignments()` | `DesignAssignmentViewSet.list` |
| `POST` | `/api/design-studio/assignments/` | Assign design task to designer | `api.assignDesignWork()` | `DesignAssignmentViewSet.create` |
| `POST` | `/api/design-studio/assignments/{id}/submit/` | Designer submits finished work | `api.submitDesignAssignment()` | `DesignAssignmentViewSet.submit` |
| `POST` | `/api/design-studio/assignments/{id}/review/` | Supervisor reviews submitted work | `api.reviewDesignAssignment()` | `DesignAssignmentViewSet.review` |

---


| Method | Endpoint | Connected Functionality | Frontend API Method | Backend Handler / Domain |
|---|---|---|---|---|
| `GET` | `/api/inventory/items/` | List inventory items | `api.getInventoryItems()` | `InventoryItemViewSet.list` |
| `POST` | `/api/inventory/items/` | Add inventory item | `api.saveInventoryItem()` | `InventoryItemViewSet.create` |
| `GET` | `/api/inventory/items/summary/` | Stock summary & alerts | `api.getInventorySummary()` | `InventoryItemViewSet.summary` |
| `POST` | `/api/inventory/items/{id}/{movement}/` | Execute stock movement (`stock-in`, `reserve`, `issue`, `return`, `scrap`, etc.) | `api.moveStock()` | `InventoryItemViewSet.<movement>` |
| `GET` | `/api/inventory/items/{id}/movements/` | View item stock movement history | `api.getItemMovements()` | `InventoryItemViewSet.movements` |
| `GET/POST` | `/api/inventory/suppliers/` | Supplier management | `api.getSuppliers()`, `api.createSupplier()` | `SupplierViewSet` |
| `GET/POST` | `/api/inventory/purchase-orders/` | Purchase order tracking & creation | `api.getPurchaseOrders()`, `api.createPurchaseOrder()` | `PurchaseOrderViewSet` |
| `POST` | `/api/inventory/purchase-orders/{id}/receive/` | Receive goods into inventory | `api.receivePurchaseOrder()` | `PurchaseOrderViewSet.receive` |
| `GET` | `/api/inventory/catalog/items/sections/` | Catalog sections | `api.getCatalogSections()` | `CatalogSectionViewSet` |
| `GET` | `/api/inventory/catalog/items/` | Raw materials catalog | `api.getCatalogItems()` | `CatalogItemViewSet` |
| `GET` | `/api/inventory/locations/` | Stock storage locations | `api.getStockLocations()` | `StockLocationViewSet` |
| `POST` | `/api/inventory/items/{id}/transfer/` | Transfer stock between locations | `api.transferStock()` | `InventoryItemViewSet.transfer` |
| `GET/POST` | `/api/inventory/boms/` | Bill of Materials (BOM recipes) | `api.getBoms()`, `api.createBom()` | `BillOfMaterialsViewSet` |
| `POST` | `/api/inventory/boms/{id}/requirements/` | Calculate required material quantity | `api.getBomRequirements()` | `BillOfMaterialsViewSet.requirements` |
| `GET/POST` | `/api/inventory/material-plans/` | Order Material Planning | `api.getMaterialPlans()`, `api.planMaterials()` | `OrderMaterialPlanViewSet` |
| `POST` | `/api/inventory/material-plans/{id}/reserve/` | Reserve planned materials | `api.reservePlan()` | `OrderMaterialPlanViewSet.reserve` |
| `POST` | `/api/inventory/material-plans/{id}/consume/` | Consume planned materials | `api.consumePlanLine()` | `OrderMaterialPlanViewSet.consume` |
| `POST` | `/api/inventory/material-plans/{id}/release-unused/` | Return unused reserved stock | `api.releasePlanUnused()` | `OrderMaterialPlanViewSet.release_unused` |
| `GET/POST` | `/api/inventory/customer-materials/` | Track materials provided by client | `api.getCustomerMaterials()`, `api.receiveCustomerMaterial()` | `CustomerMaterialViewSet` |
| `GET` | `/api/inventory/reports/{name}/` | View stock reports | `api.getInventoryReport()` | `InventoryReportViewSet` |

---


| Method | Endpoint | Connected Functionality | Frontend API Method | Backend Handler / Domain |
|---|---|---|---|---|
| `GET` | `/api/catalog/templates/` | List garment templates (Lehenga, Suit, etc.) | `api.getGarmentTemplates()` | `GarmentTemplateViewSet.list` |
| `GET` | `/api/catalog/templates/{key}/` | Get template structure & measurement keys | `api.getGarmentTemplate()` | `GarmentTemplateViewSet.retrieve` |
| `GET/POST` | `/api/catalog/jobs/` | Manage order garment job entries | `api.getGarmentJobs()`, `api.createGarmentJob()` | `GarmentJobViewSet` |

---


| Method | Endpoint | Connected Functionality | Frontend API Method | Backend Handler / Domain |
|---|---|---|---|---|
| `GET` | `/api/scheduling/appointments/` | Fetch upcoming trial & consultation appointments | `api.getAppointments()` | `AppointmentViewSet.list` |
| `POST` | `/api/scheduling/appointments/` | Book customer appointment | `api.createAppointment()` | `AppointmentViewSet.create` |

---


| Method | Endpoint | Connected Functionality | Frontend API Method | Backend Handler / Domain |
|---|---|---|---|---|
| `GET` | `/api/dashboard/` | Boutique analytics, revenue & order stats | `api.getDashboard()` | `crm_api.views.DashboardView` |
| `GET` | `/api/notifications/` | View system notifications & task alerts | `api.getNotifications()` | `crm_api.views.NotificationViewSet.list` |
| `POST` | `/api/notifications/mark-all-read/` | Mark notifications read | `api.markNotificationsAsRead()` | `NotificationViewSet.mark_all_read` |
| `GET/POST` | `/api/boutique-settings/` | Get & Update boutique branding, hours & rules | `api.getBoutiqueSettings()`, `api.updateBoutiqueSettings()` | `crm_api.views.BoutiqueSettingsViewSet` |

---


| Method | Endpoint | Connected Functionality | Frontend API Method (`src/superadmin/api.js`) | Backend Handler |
|---|---|---|---|---|
| `POST` | `/api/superadmin/auth/login/` | Superadmin Console Sign In | `consoleApi.login()` | `superadmin.views.PlatformLoginView` |
| `GET` | `/api/superadmin/auth/me/` | Superadmin profile check | `consoleApi.me()` | `superadmin.views.PlatformMeView` |
| `GET` | `/api/superadmin/overview/` | Platform-wide cross-tenant metrics | `consoleApi.overview()` | `superadmin.views.OverviewView` |
| `GET` | `/api/superadmin/boutiques/` | List registered tenant boutiques | `consoleApi.datasets()` | `superadmin.views.TenantViewSet.list` |
| `POST` | `/api/superadmin/boutiques/{schema}/suspend/` | Suspend tenant access | `consoleApi.suspend()` | `TenantViewSet.suspend` |
| `POST` | `/api/superadmin/boutiques/{schema}/reactivate/` | Reactivate suspended tenant | `consoleApi.reactivate()` | `TenantViewSet.reactivate` |
| `GET` | `/api/superadmin/boutiques/{schema}/data/` | Inspect tenant database models | `consoleApi.datasets()` | `superadmin.views.BoutiqueDataView` |
| `GET` | `/api/superadmin/users/` | Platform global user list | `consoleApi.users()` | `superadmin.api_views.UsersView` |
| `POST` | `/api/superadmin/users/{schema}/{user}/{act}/` | Perform administrative action on user | `consoleApi.userAction()` | `superadmin.api_views.UserActionView` |
| `GET` | `/api/superadmin/onboarding/` | Track tenant onboarding completion | `consoleApi.onboarding()` | `superadmin.api_views.OnboardingView` |
| `PATCH` | `/api/superadmin/boutiques/{schema}/modules/` | Enable/Disable feature modules | `consoleApi.setModules()` | `superadmin.api_views.BoutiqueModulesView` |
| `GET/POST/PATCH/DEL` | `/api/superadmin/flags/` | Platform feature flag control | `consoleApi.flags()`, `createFlag()` | `superadmin.api_views.FlagsView` |
| `GET/PUT` | `/api/superadmin/config/` | System configuration key-values | `consoleApi.config()`, `setConfig()` | `superadmin.api_views.ConfigView` |
| `GET` | `/api/superadmin/health/` | System & DB health checks | `consoleApi.health()` | `superadmin.api_views.HealthView` |
| `GET/PATCH` | `/api/superadmin/errors/` | Exception logs & error diagnostics | `consoleApi.errors()`, `updateError()` | `superadmin.api_views.ErrorsView` |
| `GET` | `/api/superadmin/audit/` | Audit log trail | `consoleApi.audit()` | `superadmin.api_views.AuditView` |
| `GET` | `/api/superadmin/orders/` | Global multi-tenant order monitor | `consoleApi.ordersMonitor()` | `superadmin.api_views.OrdersMonitorView` |
| `GET` | `/api/superadmin/search/` | Superadmin global search | `consoleApi.search()` | `superadmin.api_views.SearchView` |
| `GET` | `/api/superadmin/support/{schema}/` | Support impersonation mode | `consoleApi.support()` | `superadmin.api_views.SupportView` |
| `GET/PATCH` | `/api/superadmin/leads/` | Public demo leads pipeline | `consoleApi.leads()`, `updateLead()` | `superadmin.views.LeadViewSet` |

---


| Method | Endpoint | Connected Functionality | Frontend / External User | Backend Handler |
|---|---|---|---|---|
| `GET` | `/track/{token}/` | Public Customer Order Tracking Page | Order Tracking Link | `crm_api.tracking_views.order_tracking` |
| `POST` | `/demo-request/` | Public Demo Request Form (with Honeypot & Rate limiting) | Public Landing Page | `tenants.views.demo_request` |

---



```
[ Step 1: Customer Profile ]
POST /api/customers/ (Create client profile with contact info & measurements)
          │
          ▼
[ Step 2: Design Selection ]
POST /api/customers/{id}/design-preferences/ (Upload inspiration images or pick from catalog)
GET  /api/customers/{id}/ai-suggestions/ (Get AI design & style recommendations)
POST /api/customers/{id}/design-preferences/{pref_id}/approve/ (Sign off approved design)
          │
          ▼
[ Step 3: Fabric Selection ]
POST /api/customers/{id}/fabric-selections/ (Select boutique fabric stock or record customer material)
          │
          ▼
[ Step 4: Order Draft or Direct Order Creation ]
POST /api/order-drafts/ (Save draft to allow multi-session order entry)
POST /api/order-drafts/{id}/confirm/ OR POST /api/customers/{id}/create-order/
          │
          ▼
[ Result ]
Order created in Database (Status: UNASSIGNED / IN_PRODUCTION)
Order Tracking Link & Unique Token generated for Client
Notifications dispatched to Master & Owner
```

---


```
                        [ Order Placed ]
                               │
                               ▼
               POST /api/orders/{id}/assign-stage/
         (Assign Artisan/Tailor to Stage: e.g., Cutting)
                               │
                               ▼
             POST /api/orders/{id}/transition/
    (Stage: CUTTING -> Completed with images & notes)
                               │
                               ▼
             POST /api/orders/{id}/transition/
   (Stage: EMBROIDERY -> Completed with images & notes)
                               │
                               ▼
             POST /api/orders/{id}/transition/
    (Stage: STITCHING -> Completed with images & notes)
                               │
                               ▼
        PATCH /api/orders/{id}/master-verification/
(Master Quality Verification Checklist: Fit, Finishing, Measurements Checked)
                               │
                               ▼
        PATCH /api/orders/{id}/submit-completion/
      (Tailor submits final photograph of completed garment)
                               │
                               ▼
       POST /api/orders/{id}/publish-garment-images/
(Publish garment photo -> Triggers WhatsApp customer notification ready for trial)
                               │
                               ▼
        PATCH /api/orders/{id}/update-status/
                   (Status -> DELIVERED)
```

---


```
[ Order Garment Job Created ]
             │
             ▼
POST /api/inventory/boms/{id}/requirements/
(Calculate fabric, thread, zipper & trim quantities needed)
             │
             ▼
POST /api/inventory/material-plans/plan/
(Create Material Plan for Order)
             │
             ▼
POST /api/inventory/material-plans/{id}/reserve/
(Reserve required items in stock location -> Ledger records movement: RESERVE)
             │
             ▼
POST /api/inventory/material-plans/{id}/consume/
(Deduct stock as tailors cut fabric -> Ledger records movement: CONSUME)
             │
             ▼
POST /api/inventory/material-plans/{id}/release-unused/
(Return leftover fabric to main stock location)
```

---


```
[ Customer receives WhatsApp SMS with tracking URL: /track/<token>/ ]
                               │
                               ▼
               GET /track/<token>/ (Public API endpoint)
                               │
                               ▼
             Validate token against Order table
                               │
                               ▼
Return Customer View:
- Live Stage Timeline (Cutting -> Stitching -> Trial -> Delivered)
- Scheduled Fitting / Trial Date
- Published Garment Photographs
- Boutique Contact Information
```

---


```
                 [ Platform Admin Signs In ]
          POST /api/superadmin/auth/login/ (Public Schema)
                               │
                               ▼
                GET /api/superadmin/overview/
  (Cross-tenant dashboard: MRR, total orders, active boutiques)
                               │
                               ▼
              GET /api/superadmin/boutiques/
    (List all tenants & monitor database health / error rates)
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
POST /api/superadmin/boutiques/{schema}/suspend/    PATCH /api/superadmin/boutiques/{schema}/modules/
(Suspend non-paying boutique)                   (Toggle premium inventory or design module)
```

---


| Domain Service | File Path | Responsible For |
|---|---|---|
| `OrderService` | `domains/orders/services.py` | Order state transitions, stage assignments, staff availability checks. |
| `CustomerRepository` | `domains/customers/repositories.py` | Customer queries, summary querysets, relationship hydration. |
| `OrderRepository` | `domains/orders/repositories.py` | Order data access, filtering visible orders per role. |
| `drafts` | `domains/orders/drafts.py` | Optimistic locking, draft validation, atomic draft conversion. |
| `tracking` | `domains/orders/tracking.py` | Order tracking token generation and URL signing. |
| `messaging` | `domains/orders/messaging.py` | Customer notification queuing (WhatsApp links). |
| `notifications` | `domains/orders/notifications.py` | Internal notification triggers on order events. |
| `TenantHeaderMiddleware` | `tenants/middleware.py` | Dynamic database schema routing per HTTP request. |
