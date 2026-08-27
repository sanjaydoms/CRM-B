
from django.conf import settings
from django.utils.module_loading import import_string

from .rules import RuleBasedIntelligence

_DEFAULT = 'apps.design_studio.intelligence.rules.RuleBasedIntelligence'
_cache = {}


def get_intelligence():
    path = getattr(settings, 'DESIGN_STUDIO_INTELLIGENCE', _DEFAULT) or _DEFAULT
    if path not in _cache:
        try:
            _cache[path] = import_string(path)()
        except ImportError:
            _cache[path] = RuleBasedIntelligence()
    return _cache[path]
