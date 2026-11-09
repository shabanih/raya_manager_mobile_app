"""Compatibility facade for the mobileApp API views.

Existing imports in urls.py remain valid: ``from .views import SomeAPIView``.
Implementations live in api_views/*.py.
"""
import sys as _sys
from .api_views import (
    authentication,
    dashboards,
    resident_charges,
    announcements_polls,
    civil_charges,
    sewage_charges,
    payments_messages,
    manager_communications,
    manager_polls,
    support,
    units,
    manager_charges,
    charge_calculations,
    finance,
    reports,
    subscriptions_payments,
    app,
    bank_reports,
)

from .api_views.authentication import *  # noqa: F401,F403
from .api_views.dashboards import *  # noqa: F401,F403
from .api_views.resident_charges import *  # noqa: F401,F403
from .api_views.announcements_polls import *  # noqa: F401,F403
from .api_views.civil_charges import *  # noqa: F401,F403
from .api_views.sewage_charges import *  # noqa: F401,F403
from .api_views.payments_messages import *  # noqa: F401,F403
from .api_views.manager_communications import *  # noqa: F401,F403
from .api_views.manager_polls import *  # noqa: F401,F403
from .api_views.support import *  # noqa: F401,F403
from .api_views.units import *  # noqa: F401,F403
from .api_views.manager_charges import *  # noqa: F401,F403
from .api_views.charge_calculations import *  # noqa: F401,F403
from .api_views.finance import *  # noqa: F401,F403
from .api_views.reports import *  # noqa: F401,F403
from .api_views.subscriptions_payments import *  # noqa: F401,F403
from .api_views.app import *  # noqa: F401,F403
from .api_views.bank_reports import *  # noqa: F401,F403

# Make cross-module references to view classes and helper functions available at runtime.
# Base classes are kept together with their subclasses during extraction; this injection
# handles method-body references without introducing circular imports.
_modules = [
    authentication,
    dashboards,
    resident_charges,
    announcements_polls,
    civil_charges,
    sewage_charges,
    payments_messages,
    manager_communications,
    manager_polls,
    support,
    units,
    manager_charges,
    charge_calculations,
    finance,
    reports,
    subscriptions_payments,
    app,
    bank_reports,
]
_shared = {}
for _module in _modules:
    for _name, _value in vars(_module).items():
        if not _name.startswith("_"):
            _shared[_name] = _value
for _module in _modules:
    for _name, _value in _shared.items():
        if not hasattr(_module, _name):
            setattr(_module, _name, _value)

del _module, _modules, _shared, _name, _value
