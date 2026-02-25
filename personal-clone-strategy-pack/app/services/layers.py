"""Layer service — backward-compatible re-exports from domain modules.

All layer functions are now organized in app/services/layers_pkg/:
  - marketing.py: get_marketing_layer, get_study_layer
  - people.py: training, employee perf/mgmt, revenue, staff, AI routing, prosperity
  - clone.py: clone training, clone marketing/sales, opportunity association
  - intelligence.py: threat, branding, fraud, ethics, media, social (thin proxies)

This file re-exports every function so existing imports from
``app.services.layers`` continue to work without changes.
"""
from app.services.layers_pkg.marketing import (  # noqa: F401
    get_marketing_layer,
    get_study_layer,
)
from app.services.layers_pkg.people import (  # noqa: F401
    get_training_layer,
    get_employee_performance_layer,
    get_employee_management_layer,
    get_revenue_management_layer,
    get_staff_training_layer,
    get_ai_skill_routing_layer,
    get_staff_prosperity_layer,
)
from app.services.layers_pkg.clone import (  # noqa: F401
    get_clone_training_layer,
    get_clone_marketing_sales_layer,
    get_opportunity_association_layer,
)
from app.services.layers_pkg.intelligence import (  # noqa: F401
    get_threat_detection_layer,
    get_branding_power_layer,
    get_fraud_detection_layer,
    get_ethical_boundary_layer,
    get_media_editing_layer,
    get_social_management_layer,
)
