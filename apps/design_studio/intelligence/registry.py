"""Resolves the configured intelligence implementation.

Set ``DESIGN_STUDIO_INTELLIGENCE`` to a dotted path to swap in a model-backed
engine. Unset, the studio uses the deterministic rules and needs no
credentials.
"""

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
            # A misconfigured path must not take the order wizard down with it;
            # fall back to the engine that always works.
            _cache[path] = RuleBasedIntelligence()
    return _cache[path]
