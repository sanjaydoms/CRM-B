"""The console's own tables. All four live in the public schema.

`superadmin` is in SHARED_APPS only, so these exist once for the platform rather
than once per boutique. That is the point: an audit trail scattered across fifty
schemas cannot answer "who suspended this boutique", and an error feed that has
to be assembled with fifty schema switches is not a feed.

Everything the console *shows* about a boutique is still read live from that
boutique's schema (superadmin/metrics.py, superadmin/datasets.py). Nothing here
duplicates business data. These four models record things the product previously
did not record at all:

  AuditLog      who did what through the console, and what the value was before.
  ErrorEvent    unhandled exceptions, which nothing captured -- with DEBUG off
                and no ADMINS configured, a 500 reached nobody at all.
  FeatureFlag   a switch that can be flipped without a deploy.
  PlatformSetting  platform-wide configuration, including maintenance mode.
"""

from django.db import models


class AuditLog(models.Model):
    """An append-only record of every sensitive action taken in the console.

    Deliberately not a ForeignKey to anything. The target of an audit entry can
    be a boutique, a user inside a boutique's schema, a feature flag or a
    setting -- and two of those are not reachable by FK from the public schema
    at all. More importantly, an audit row must survive the deletion of whatever
    it describes; a cascade would erase exactly the history of the event most
    worth keeping.

    `before` and `after` are JSON rather than text so a change can be diffed
    rather than read as prose.

    Append-only is enforced by convention and by the API (the console exposes no
    write route), not by the database. Postgres can be told to refuse UPDATE and
    DELETE on this table with a rule or a restricted role; that is a deployment
    decision rather than something a migration should impose on a developer's
    laptop, and it is written up in the README.
    """

    ACTIONS = [
        ('boutique.suspend', 'Boutique suspended'),
        ('boutique.reactivate', 'Boutique reactivated'),
        ('boutique.modules', 'Boutique modules changed'),
        ('user.deactivate', 'User deactivated'),
        ('user.activate', 'User activated'),
        ('user.revoke_token', 'User sessions revoked'),
        ('user.password_reset', 'Password reset triggered'),
        ('lead.update', 'Lead updated'),
        ('flag.change', 'Feature flag changed'),
        ('setting.change', 'Platform setting changed'),
        ('error.acknowledge', 'Error acknowledged'),
        ('error.resolve', 'Error resolved'),
        ('data.view', 'Boutique data viewed'),
        ('console.login', 'Console sign-in'),
        ('console.login_failed', 'Console sign-in failed'),
    ]

    actor = models.CharField(
        max_length=150, db_index=True,
        help_text="Username of the administrator. Stored as text, not a FK, so "
                  "the entry outlives the account.")
    action = models.CharField(max_length=40, choices=ACTIONS, db_index=True)

    #: What was acted on: a schema name, a username, a flag key. Free text
    #: because the target space is heterogeneous -- see the class docstring.
    target = models.CharField(max_length=255, blank=True, db_index=True)
    #: The boutique this concerns, where it concerns one. Schema name rather
    #: than an FK for the same reason.
    boutique = models.CharField(max_length=63, blank=True, db_index=True)

    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)

    #: Why. Required by the API for the destructive actions, blank for the rest.
    reason = models.TextField(blank=True)

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            # The three queries the console actually runs: a boutique's history,
            # one administrator's history, and "what happened to this thing".
            models.Index(fields=['boutique', '-created_at']),
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.actor} {self.action} {self.target}'


class ErrorEvent(models.Model):
    """One *kind* of unhandled exception, with a count -- not one row per crash.

    Grouped by `fingerprint`, because the failure mode of an error table is that
    a single broken endpoint hit a thousand times buries every other problem.
    The console shows fifty distinct problems rather than the same one fifty
    times, and `count` is what makes an error urgent.

    Captured by core/exceptions.py, which is wired in as DRF's EXCEPTION_HANDLER.
    Before that existed nothing recorded a 500 anywhere: there is no LOGGING
    config, DEBUG is off in production, and ADMINS is empty, so Django's default
    mail_admins handler had no recipient.
    """

    SEVERITIES = [('critical', 'Critical'), ('high', 'High'),
                  ('medium', 'Medium'), ('low', 'Low')]
    STATUSES = [('new', 'New'), ('acknowledged', 'Acknowledged'),
                ('resolved', 'Resolved'), ('ignored', 'Ignored')]

    #: sha1 of exception class + normalised path + the last in-project frame.
    #: Stable across occurrences of the same bug, different for different bugs.
    fingerprint = models.CharField(max_length=40, unique=True, db_index=True)

    exception_type = models.CharField(max_length=200, db_index=True)
    message = models.TextField()
    #: Only the frames inside this project, innermost last. Vendor frames are
    #: dropped -- they are the same twenty lines on every entry and they push
    #: the line that matters off the screen.
    traceback = models.TextField(blank=True)

    path = models.CharField(max_length=300, db_index=True)
    method = models.CharField(max_length=10, blank=True)
    status_code = models.PositiveSmallIntegerField(default=500)

    #: The boutique of the MOST RECENT occurrence -- it is overwritten every
    #: time, so it is not "the affected boutique" and must not be read as one.
    #: Schema name, not an FK: an error is often *about* a tenant that is broken.
    boutique = models.CharField(max_length=63, blank=True, db_index=True)
    #: Every boutique this bug has been seen in, which is the question the
    #: column above cannot answer. A bug hitting forty boutiques used to report
    #: only the fortieth and leave the other thirty-nine unattributable.
    #: Capped -- see _BOUTIQUE_LIST_LIMIT in core/exceptions.py -- so the row
    #: does not grow with the tenant count on every occurrence; past the cap
    #: this reads "at least these", and len() is a floor on the distinct count.
    boutiques = models.JSONField(default=list, blank=True)
    #: Username only. Never the token, never the request body: a crash report
    #: that quietly copies whatever the user was submitting is a data leak with
    #: a stack trace attached.
    username = models.CharField(max_length=150, blank=True)

    severity = models.CharField(max_length=10, choices=SEVERITIES, default='high', db_index=True)
    status = models.CharField(max_length=12, choices=STATUSES, default='new', db_index=True)

    count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen = models.DateTimeField(auto_now=True, db_index=True)

    notes = models.TextField(blank=True)
    resolved_by = models.CharField(max_length=150, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_seen']
        indexes = [
            models.Index(fields=['status', '-last_seen']),
            models.Index(fields=['severity', '-last_seen']),
            models.Index(fields=['boutique', '-last_seen']),
        ]

    def __str__(self):
        return f'{self.exception_type} at {self.path} (x{self.count})'


class FeatureFlag(models.Model):
    """A switch that can be flipped without a deploy.

    Distinct from a module (core/modules.py): a module is an existing product
    surface an administrator withholds from a boutique, while a flag is a
    behaviour the code itself asks about. `enabled_for` narrows a global-off
    flag to named boutiques, which is what makes a beta possible.

    `rollout_percent` is a bucketed hash of the schema name, not a coin flip --
    a boutique that is in the rollout must stay in it, or a half-released
    feature appears and disappears between requests.
    """

    key = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)

    #: Schema names this is on for regardless of `enabled`.
    enabled_for = models.JSONField(default=list, blank=True)
    rollout_percent = models.PositiveSmallIntegerField(default=0)

    created_by = models.CharField(max_length=150, blank=True)
    modified_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return f'{self.key} ({"on" if self.enabled else "off"})'

    def applies_to(self, schema_name):
        """Whether this flag is on for one boutique."""
        if schema_name and schema_name in (self.enabled_for or []):
            return True
        if self.enabled:
            return True
        if self.rollout_percent and schema_name:
            # Stable bucket: the same boutique always lands in the same slot, so
            # a feature at 20% does not flicker on and off for the same people.
            import hashlib
            digest = hashlib.sha1(f'{self.key}:{schema_name}'.encode()).hexdigest()
            return int(digest[:8], 16) % 100 < self.rollout_percent
        return False


class PlatformSetting(models.Model):
    """Platform-wide configuration, as key/value rows rather than columns.

    Rows rather than a settings model with one column per option, because these
    are read by the console and written by the console and a new option should
    not need a migration. Anything the *code* needs at import time belongs in
    settings.py, not here.

    Maintenance mode lives here and is enforced in tenants/middleware.py.
    """

    key = models.SlugField(max_length=80, unique=True)
    value = models.JSONField(null=True, blank=True)
    description = models.TextField(blank=True)
    updated_by = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.key
