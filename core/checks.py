"""Deploy-time guards on the module registry.

The point of this file: /api/email/ and /api/order-drafts/ were both mounted
months after core/modules.py was written and neither was governed by anything.
The platform console could switch a boutique's modules off and those two
prefixes answered anyway. Nothing warned anybody, because nothing was looking.

So something looks now, on every `manage.py check` -- which is to say on every
deploy. A new prefix is an ERROR, not a warning: a warning scrolls past in a
build log and the next Marketing or Try-On module lands exactly the way these
two did.
"""

import re

from django.core.checks import Error, register
from django.urls import URLResolver, get_resolver

from .modules import (
    ALL_ROLES, ALWAYS_ON, GROUPS, MODULE_GROUP, MODULES, OWNER, ROLE_DEFAULTS,
    module_for_path,
)

#: A path segment with nothing regex-ish or converter-ish in it. Anything else
#: ends the literal head: '/api/orders/(?P<pk>[^/.]+)/' is mounted at
#: '/api/orders/', and that is the prefix a module governs.
_LITERAL = re.compile(r'[-\w.~]*\Z')

#: Where the STRUCTURAL modules are mounted. Written out rather than inferred
#: from the key: f'/api/{key}/' is a key-equals-URL convention MODULES
#: deliberately does not use ('inventory_catalog' is mounted at
#: '/api/inventory/catalog/', 'design_studio' at two prefixes), so inferring it
#: here wrote the orders and customers mount points down a second time,
#: implicitly, where renaming either key would silently move the prefix this
#: check trusts.
#: ponytail: these belong beside the label and reason in modules.STRUCTURAL,
#: the way MODULES carries its own prefixes. That is a 2-tuple three call sites
#: unpack (catalogue() among them) and modules.py is not this file to change;
#: move them there when STRUCTURAL grows a prefixes slot. Until then a
#: structural module added without a line here is not silent -- its mount point
#: is ungoverned, so core.E001 reports it.
_STRUCTURAL_PREFIXES = ('/api/orders/', '/api/customers/')


def _literal_head(pattern):
    """'orders/(?P<pk>[^/.]+)/$' -> '/orders/'. No literal segment -> '/'."""
    kept = []
    for segment in str(pattern).lstrip('^').split('/'):
        if not _LITERAL.match(segment):
            break
        kept.append(segment)
    head = '/' + '/'.join(kept).strip('/')
    return head if head.endswith('/') else head + '/'


def _accounted_for(prefix):
    """The three legitimate answers, in the order the request meets them."""
    if any(prefix.startswith(always) for always in ALWAYS_ON):
        return 'always-on'
    key = module_for_path(prefix)
    if key is not None:
        return f'module {key!r}'
    # startswith, like ALWAYS_ON: STRUCTURAL says the whole prefix is one
    # inseparable thing, so /api/orders/customer-messages/ is covered by the
    # same judgement that covers /api/orders/.
    if any(prefix.startswith(s) for s in _STRUCTURAL_PREFIXES):
        return 'structural'
    return None


def mounted_prefixes(patterns=None, base='/'):
    """Every prefix the URLconf actually mounts, coarsest first.

    Descends only into a prefix nothing accounts for yet -- '/api/' has to be
    opened up to find order-drafts, '/admin/' does not, and stopping there
    keeps three hundred admin routes out of the answer.
    """
    if patterns is None:
        patterns = get_resolver().url_patterns
    for pattern in patterns:
        own = _literal_head(pattern.pattern)
        if isinstance(pattern, URLResolver):
            # An include() mounted at '' (crm_api's DefaultRouter) adds no
            # segment of its own; its children still do.
            full = base if own == '/' else base + own.lstrip('/')
            if _accounted_for(full):
                yield full
                continue
            found = False
            for child in mounted_prefixes(pattern.url_patterns, full):
                found = True
                yield child
            # Descending found nothing, so there is nothing below the mount
            # point to judge and the mount point itself is the thing to judge.
            # This is the hole that made the whole check false comfort:
            # include([path('', view)]) mounts an entire app at
            # /api/marketing-b/ and adds no literal segment under it, so the
            # walk descended into silence and core.E001 passed clean on an app
            # no module governed. Yielding `full` unconditionally is not the
            # fix -- it would report '/api/' itself, which is governed by
            # nothing and MUST be opened up rather than judged.
            #
            # A resolver mounted at '' is exempt: it adds no segment, so `full`
            # is its parent's prefix and judging it would answer for a mount
            # point this level did not create. Whoever mounted the parent is
            # who gets judged.
            if not found and own != '/':
                yield full
        elif own != '/':
            yield base + own.lstrip('/')
        # A leaf adding no literal segment is the mount point itself -- the
        # router's api-root and its '\.(?P<format>...)' twins. Already judged
        # by whatever mounted it. A mixed app (a root view AND child routes)
        # is judged the same way as /api/ is: its children are reported and
        # the root view rides on whatever prefix governs them, because
        # governance is startswith-shaped and registering the app's mount
        # point covers both.


@register()
def check_every_prefix_is_governed(app_configs, **kwargs):
    errors = []
    for prefix in sorted(set(mounted_prefixes())):
        if _accounted_for(prefix):
            continue
        errors.append(Error(
            f"{prefix} is mounted but no module governs it.",
            hint=("Add it to MODULES in core/modules.py (with a MODULE_GROUP "
                  "entry and a place in ROLE_DEFAULTS), or to ALWAYS_ON if it "
                  "must answer for every boutique, or to STRUCTURAL if it "
                  "carries so much that gating it would switch off unrelated "
                  "features. Until then the platform console cannot switch it "
                  "off and no role gate applies to it."),
            id='core.E001',
        ))
    return errors


@register()
def check_registry_is_consistent(app_configs, **kwargs):
    """Typos here fail silently and look like a permissions bug forever.

    A misspelt role name in ROLE_DEFAULTS grants that role nothing and denies
    nobody anything -- there is no exception, no log line, just a tailor who
    cannot open a screen and a map that reads correct.
    """
    errors = []

    ungrouped = sorted(set(MODULES) - set(MODULE_GROUP))
    if ungrouped:
        errors.append(Error(
            f"Modules with no group: {', '.join(ungrouped)}.",
            hint="Add each to MODULE_GROUP in core/modules.py.",
            id='core.E002'))
    for key, group in sorted(MODULE_GROUP.items()):
        if key not in MODULES:
            errors.append(Error(
                f"MODULE_GROUP names {key!r}, which is not a module.",
                id='core.E003'))
        if group not in GROUPS:
            errors.append(Error(
                f"MODULE_GROUP puts {key!r} in group {group!r}, which is not in GROUPS.",
                id='core.E004'))

    expected = set(ALL_ROLES) - {OWNER}
    missing = sorted(expected - set(ROLE_DEFAULTS))
    if missing:
        errors.append(Error(
            f"Roles with no default access: {', '.join(missing)}.",
            hint=("Add each to ROLE_DEFAULTS in core/modules.py. A role that "
                  "is absent falls back to the Tailor defaults, which is the "
                  "right answer for a role nobody has heard of and the wrong "
                  "one for a role this codebase defines."),
            id='core.E005'))
    for role, keys in sorted(ROLE_DEFAULTS.items()):
        if role == OWNER:
            errors.append(Error(
                "ROLE_DEFAULTS must not list the Owner.",
                hint=("role_allows() returns True for the owner on anything "
                      "the boutique is entitled to. An entry here reads as a "
                      "second, weaker answer."),
                id='core.E006'))
        elif role not in ALL_ROLES:
            errors.append(Error(
                f"ROLE_DEFAULTS names {role!r}, which is not a role.",
                hint=f"Roles are {', '.join(ALL_ROLES)}.",
                id='core.E007'))
        unknown = sorted(set(keys) - set(MODULES))
        if unknown:
            errors.append(Error(
                f"ROLE_DEFAULTS[{role!r}] names modules that do not exist: "
                f"{', '.join(unknown)}.",
                id='core.E008'))
    return errors


@register()
def check_production_roles_match_the_model(app_configs, **kwargs):
    """PRODUCTION_ROLES is a copy of Tailor.ROLE_CHOICES; keep it one.

    modules.py cannot import the model -- it is loaded by middleware before a
    tenant schema is set -- so the copy is deliberate. This is what stops it
    rotting: a tenth role added to the model without being added here would
    silently get the Tailor defaults and nobody would know which.
    """
    from .modules import PRODUCTION_ROLES
    try:
        from crm_api.models import Tailor
        model_roles = tuple(role for role, _label in Tailor.ROLE_CHOICES)
    except Exception as exc:
        # Not `return []`. Swallowing this is how the guard goes dead without
        # anybody noticing: a rename, a moved model or a broken import turns
        # the one thing keeping PRODUCTION_ROLES honest into a no-op that
        # still reports "no issues". Being unable to check IS the problem.
        return [Error(
            "Could not read Tailor.ROLE_CHOICES, so PRODUCTION_ROLES is unchecked.",
            hint=(f"{type(exc).__name__}: {exc}. Fix the import or move the "
                  "check to wherever the roles now live -- do not leave it "
                  "passing on a guard that cannot run."),
            id='core.E010')]
    if model_roles != PRODUCTION_ROLES:
        return [Error(
            "PRODUCTION_ROLES no longer matches Tailor.ROLE_CHOICES.",
            hint=f"Model has {model_roles}; core/modules.py has {PRODUCTION_ROLES}.",
            id='core.E009')]
    return []
