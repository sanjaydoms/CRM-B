from crm_api.models import Tailor, BoutiqueFabric, BoutiqueDesign

def seed_tenant_defaults():
    # Seed Tailors
    tailors = [
        {"name": "Rohit Mehra", "specialty": "Ethnic & Bridal Cutting", "rating": 4.90, "status": "Available", "role": "Master"},
        {"name": "Anya Sharma", "specialty": "Blouse & Lehenga Specialist", "rating": 4.80, "status": "Available", "role": "Tailor"},
        {"name": "Rahul Verma", "specialty": "Suit & Gown Specialist", "rating": 4.70, "status": "Available", "role": "Tailor"},
        {"name": "Preeti Singh", "specialty": "Embroidery Specialist", "rating": 4.95, "status": "Available", "role": "Tailor"},
    ]

    for t in tailors:
        Tailor.objects.get_or_create(
            name=t["name"],
            defaults={"specialty": t["specialty"], "rating": t["rating"], "status": t["status"], "role": t["role"]}
        )

    # Seed Boutique Fabrics
    fabrics = [
        {"name": "Silk Dupion", "material": "Pure Silk", "color": "Dusty Rose", "price_per_meter": 1850.00, "image_url": "https://images.unsplash.com/photo-1558171813-4c088753af8f?w=400"},
        {"name": "Banarasi Silk", "material": "Zari Silk", "color": "Metallic Gold", "price_per_meter": 2850.00, "image_url": "https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400"},
        {"name": "Linen Blend", "material": "Linen", "color": "Charcoal Black", "price_per_meter": 1250.00, "image_url": "https://images.unsplash.com/photo-1553775927-a071d5a6a39a?w=400"},
        {"name": "Raw Silk", "material": "Silk", "color": "Royal Blue", "price_per_meter": 1850.00, "image_url": "https://images.unsplash.com/photo-1539008835657-9e8e62c8425b?w=400"},
        {"name": "Cotton Slub", "material": "Cotton", "color": "Olive Green", "price_per_meter": 950.00, "image_url": "https://images.unsplash.com/photo-1605721911519-3dfeb3be25e7?w=400"},
    ]

    for f in fabrics:
        fab_obj, created = BoutiqueFabric.objects.get_or_create(
            name=f["name"],
            defaults={"material": f["material"], "color": f["color"], "price_per_meter": f["price_per_meter"], "image_url": f["image_url"]}
        )
        if not created and ('fabric_' in str(fab_obj.image_url) or not str(fab_obj.image_url).startswith('http')):
            fab_obj.image_url = f["image_url"]
            fab_obj.save()

    # Seed Boutique & AI Designs
    designs = [
        # AI Suggestions (is_boutique=False)
        {
            "name": "Pastel Silver Zari Lehenga",
            "garment_type": "Lehenga",
            "neckline_style": "Sweetheart",
            "sleeve_style": "Half Sleeve",
            "image_url": "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=400",
            "is_boutique": False,
            "description": "Exquisite silver zari embroidery on pastel hues.",
            "price": 0.0
        },
        {
            "name": "Crimson Red Bridal Lehenga",
            "garment_type": "Lehenga",
            "neckline_style": "Sweetheart",
            "sleeve_style": "Half Sleeve",
            "image_url": "https://images.unsplash.com/photo-1597983073492-bc24058b375b?w=400",
            "is_boutique": False,
            "description": "Traditional bridal red lehenga with intricate handcrafting.",
            "price": 0.0
        },
        {
            "name": "Classic Silk Brocade Lehenga",
            "garment_type": "Lehenga",
            "neckline_style": "Round Neck",
            "sleeve_style": "Half Sleeve",
            "image_url": "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=400",
            "is_boutique": False,
            "description": "Rich traditional Banarasi silk brocade patterns.",
            "price": 0.0
        },
        {
            "name": "Royal Blue Sequin Lehenga",
            "garment_type": "Lehenga",
            "neckline_style": "V-Neck",
            "sleeve_style": "Sleeveless",
            "image_url": "https://images.unsplash.com/photo-1597983073492-bc24058b375b?w=400",
            "is_boutique": False,
            "description": "Shimmering sequin embroidery for evening glamour.",
            "price": 0.0
        },
        {
            "name": "Ethereal Peach Georgette Gown",
            "garment_type": "Gown",
            "neckline_style": "Boat Neck",
            "sleeve_style": "Sleeveless",
            "image_url": "https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=400",
            "is_boutique": False,
            "description": "Lightweight flowing peach georgette with delicate lace highlights.",
            "price": 0.0
        },
        {
            "name": "Midnight Blue Embroidered Gown",
            "garment_type": "Gown",
            "neckline_style": "Sweetheart",
            "sleeve_style": "Full Sleeve",
            "image_url": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=400",
            "is_boutique": False,
            "description": "Deep midnight velvet overlay with floral thread embroidery.",
            "price": 0.0
        },
        {
            "name": "Golden Banarasi Silk Saree",
            "garment_type": "Saree",
            "neckline_style": "Round Neck",
            "sleeve_style": "Half Sleeve",
            "image_url": "https://images.unsplash.com/photo-1610030469668-93535c17b6b3?w=400",
            "is_boutique": False,
            "description": "Timeless golden weave Banarasi silk saree.",
            "price": 0.0
        },

        # Boutique Catalog (is_boutique=True)
        {
            "name": "Royal Maroon Velvet Lehenga",
            "garment_type": "Lehenga",
            "neckline_style": "Sweetheart",
            "sleeve_style": "Half Sleeve",
            "image_url": "https://images.unsplash.com/photo-1518049368264-7a13d7825d19?w=400",
            "is_boutique": True,
            "description": "Luxury royal velvet with hand-sewn metallic threads.",
            "price": 45000.00
        },
        {
            "name": "Ivory White Silk Gown",
            "garment_type": "Gown",
            "neckline_style": "V-Neck",
            "sleeve_style": "Cap Sleeve",
            "image_url": "https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=400",
            "is_boutique": True,
            "description": "Stunning silk gown with fine lace appliques.",
            "price": 32000.00
        },
        {
            "name": "Emerald Green Silk Saree",
            "garment_type": "Saree",
            "neckline_style": "V-Neck",
            "sleeve_style": "Half Sleeve",
            "image_url": "https://images.unsplash.com/photo-1610030469668-93535c17b6b3?w=400",
            "is_boutique": True,
            "description": "Rich emerald green Kanjivaram silk saree with traditional borders.",
            "price": 24000.00
        },
        {
            "name": "Pastel Pink Thread Lehenga",
            "garment_type": "Lehenga",
            "neckline_style": "Sweetheart",
            "sleeve_style": "Cap Sleeve",
            "image_url": "https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400",
            "is_boutique": True,
            "description": "Delicate floral thread embroidery on georgette pastel pink base.",
            "price": 38000.00
        }
    ]

    for d in designs:
        des_obj, created = BoutiqueDesign.objects.get_or_create(
            name=d["name"],
            defaults={
                "garment_type": d["garment_type"],
                "neckline_style": d["neckline_style"],
                "sleeve_style": d["sleeve_style"],
                "image_url": d["image_url"],
                "is_boutique": d["is_boutique"],
                "description": d["description"],
                "price": d["price"]
            }
        )
        if not created and ('design_' in str(des_obj.image_url) or not str(des_obj.image_url).startswith('http')):
            des_obj.image_url = d["image_url"]
            des_obj.save()

    # Seed Customers & Orders only for Sanjay's Boutique
    from django.db import connection
    if connection.schema_name == 'sanjay_garlapenta_domsglobal_co':
        from crm_api.models import Customer, Measurement, Order, OrderStage, OrderActivity
        import datetime
    
        customers_data = [
            {"first_name": "Priya", "last_name": "Patel", "mobile_number": "9876543210", "email_address": "priya@gmail.com", "city_region": "Mumbai", "customer_type": "Women", "garment_type": "Lehenga"},
            {"first_name": "Aditi", "last_name": "Sharma", "mobile_number": "9876543211", "email_address": "aditi@gmail.com", "city_region": "Delhi", "customer_type": "Women", "garment_type": "Gown"},
            {"first_name": "Rohan", "last_name": "Gupta", "mobile_number": "9876543212", "email_address": "rohan@gmail.com", "city_region": "Bangalore", "customer_type": "Men", "garment_type": "Sherwani"},
            {"first_name": "Meera", "last_name": "Nair", "mobile_number": "9876543213", "email_address": "meera@gmail.com", "city_region": "Chennai", "customer_type": "Women", "garment_type": "Saree"},
            {"first_name": "Karan", "last_name": "Johar", "mobile_number": "9876543214", "email_address": "karan@gmail.com", "city_region": "Mumbai", "customer_type": "Men", "garment_type": "Suit"}
        ]

        for c in customers_data:
            cust, created = Customer.objects.get_or_create(
                mobile_number=c["mobile_number"],
                defaults={
                    "first_name": c["first_name"],
                    "last_name": c["last_name"],
                    "email_address": c["email_address"],
                    "city_region": c["city_region"],
                    "customer_type": c["customer_type"],
                    "garment_type": c["garment_type"]
                }
            )
            if created:
                # Seed measurements
                Measurement.objects.create(
                    customer=cust,
                    bust=36.0,
                    waist=30.0,
                    hips=38.0,
                    shoulder=15.0,
                    arm_length=22.0,
                    neck=14.0,
                    length=42.0
                )

        # Fetch seeded customers and tailors
        db_customers = list(Customer.objects.all())
        db_tailors = list(Tailor.objects.all())
        master_tailor = Tailor.objects.filter(role='Master').first()
        stitching_tailor = Tailor.objects.filter(role='Tailor').first()

        # Seed Orders
        orders_data = [
            {"order_id": "T2B-260701-1001", "customer": db_customers[0] if len(db_customers) > 0 else None, "status": "Delivered", "stage_key": "delivered", "prod_status": "COMPLETED"},
            {"order_id": "T2B-260702-1002", "customer": db_customers[1] if len(db_customers) > 1 else None, "status": "Ready for Dispatch", "stage_key": "ready_for_delivery", "prod_status": "NOT_STARTED"},
            {"order_id": "T2B-260703-1003", "customer": db_customers[2] if len(db_customers) > 2 else None, "status": "Quality Check", "stage_key": "master_quality_check", "prod_status": "IN_PROGRESS"},
            {"order_id": "T2B-260704-1004", "customer": db_customers[3] if len(db_customers) > 3 else None, "status": "Design & Creation", "stage_key": "stitching_in_progress", "prod_status": "IN_PROGRESS"},
            {"order_id": "T2B-260705-1005", "customer": db_customers[4] if len(db_customers) > 4 else None, "status": "Confirmed", "stage_key": "fabric_confirmed", "prod_status": "COMPLETED"},
            {"order_id": "T2B-260706-1006", "customer": db_customers[0] if len(db_customers) > 0 else None, "status": "Received", "stage_key": "created", "prod_status": "COMPLETED"},
        ]

        stages_config = [
            {"key": "created", "name": "Created", "sla": 24},
            {"key": "measurements_completed", "name": "Measurements Completed", "sla": 24},
            {"key": "fabric_confirmed", "name": "Fabric Confirmed", "sla": 48},
            {"key": "pattern_cutting", "name": "Pattern Cutting", "sla": 48},
            {"key": "assigned_to_tailor", "name": "Assigned to Tailor", "sla": 24},
            {"key": "stitching_in_progress", "name": "Stitching In Progress", "sla": 72},
            {"key": "stitching_completed", "name": "Stitching Completed", "sla": 24},
            {"key": "master_quality_check", "name": "Master Quality Check", "sla": 24},
            {"key": "trial_scheduled", "name": "Trial Scheduled", "sla": 48},
            {"key": "trial_completed", "name": "Trial Completed", "sla": 24},
            {"key": "ready_for_delivery", "name": "Ready for Delivery", "sla": 24},
            {"key": "delivered", "name": "Delivered", "sla": 24},
        ]

        for o_data in orders_data:
            if not o_data["customer"]:
                continue
            order, created = Order.objects.get_or_create(
                order_id=o_data["order_id"],
                defaults={
                    "customer": o_data["customer"],
                    "tailor": stitching_tailor,
                    "master": master_tailor,
                    "order_status": o_data["status"],
                    "current_stage_key": o_data["stage_key"],
                    "production_status": o_data["prod_status"],
                    "base_price": 5000.00,
                    "fabric_price": 2000.00,
                    "total_amount": 7000.00,
                    "amount_paid": 3500.00,
                    "estimated_delivery": datetime.date.today() + datetime.timedelta(days=10)
                }
            )
            if created:
                # Seed stages for this order
                current_stage_reached = False
                for idx, stage in enumerate(stages_config):
                    stage_status = "NOT_STARTED"
                    started_at = None
                    completed_at = None
                    
                    # Logic to determine stage status based on reached key
                    if stage["key"] == o_data["stage_key"]:
                        stage_status = o_data["prod_status"]
                        started_at = datetime.datetime.now() - datetime.timedelta(hours=2)
                        if o_data["prod_status"] == "COMPLETED":
                            completed_at = datetime.datetime.now()
                        current_stage_reached = True
                    elif not current_stage_reached:
                        stage_status = "COMPLETED"
                        started_at = datetime.datetime.now() - datetime.timedelta(days=(12-idx))
                        completed_at = datetime.datetime.now() - datetime.timedelta(days=(11-idx))
                    else:
                        stage_status = "NOT_STARTED"

                    OrderStage.objects.create(
                        order=order,
                        stage_key=stage["key"],
                        stage_name=stage["name"],
                        status=stage_status,
                        started_at=started_at,
                        completed_at=completed_at,
                        sequence=idx,
                        sla_hours=stage["sla"],
                        performed_by=stitching_tailor if idx >= 4 else master_tailor
                    )
