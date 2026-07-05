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
        {"name": "Silk Dupion", "material": "Pure Silk", "color": "Dusty Rose", "price_per_meter": 1850.00, "image_url": "fabric_01.jpg"},
        {"name": "Banarasi Silk", "material": "Zari Silk", "color": "Metallic Gold", "price_per_meter": 2850.00, "image_url": "fabric_02.jpg"},
        {"name": "Linen Blend", "material": "Linen", "color": "Charcoal Black", "price_per_meter": 1250.00, "image_url": "fabric_03.jpg"},
        {"name": "Raw Silk", "material": "Silk", "color": "Royal Blue", "price_per_meter": 1850.00, "image_url": "fabric_04.jpg"},
        {"name": "Cotton Slub", "material": "Cotton", "color": "Olive Green", "price_per_meter": 950.00, "image_url": "fabric_05.jpg"},
    ]

    for f in fabrics:
        BoutiqueFabric.objects.get_or_create(
            name=f["name"],
            defaults={"material": f["material"], "color": f["color"], "price_per_meter": f["price_per_meter"], "image_url": f["image_url"]}
        )

    # Seed Boutique & AI Designs
    designs = [
        # AI Suggestions (is_boutique=False)
        {
            "name": "Pastel Silver Zari Lehenga",
            "garment_type": "Lehenga",
            "neckline_style": "Sweetheart",
            "sleeve_style": "Half Sleeve",
            "image_url": "design_ai_01.jpg",
            "is_boutique": False,
            "description": "Exquisite silver zari embroidery on pastel hues.",
            "price": 0.0
        },
        {
            "name": "Crimson Red Bridal Lehenga",
            "garment_type": "Lehenga",
            "neckline_style": "Sweetheart",
            "sleeve_style": "Half Sleeve",
            "image_url": "design_ai_02.jpg",
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
            "image_url": "design_cat_01.jpg",
            "is_boutique": True,
            "description": "Luxury royal velvet with hand-sewn metallic threads.",
            "price": 45000.00
        },
        {
            "name": "Ivory White Silk Gown",
            "garment_type": "Gown",
            "neckline_style": "V-Neck",
            "sleeve_style": "Cap Sleeve",
            "image_url": "design_cat_02.jpg",
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
        BoutiqueDesign.objects.get_or_create(
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
