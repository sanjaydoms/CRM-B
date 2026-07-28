"""The intelligence contract: query generation, ranking, attribute extraction.

Everything the studio calls "AI" goes through this interface. The default
implementation is deterministic and needs no credentials, so the feature works
out of the box; pointing ``DESIGN_STUDIO_INTELLIGENCE`` at a model-backed
implementation swaps the behaviour without touching the views or the gallery.
"""


class DesignIntelligence:
    key = ''

    def generate_queries(self, context, extra_keywords=None):
        """Return the search queries to run for this customer context."""
        raise NotImplementedError

    def rank(self, candidates, context):
        """Return candidates with ``match_score`` and ``match_reasons`` set."""
        raise NotImplementedError

    def analyse(self, candidate, context=None):
        """Return structured garment attributes for one design."""
        raise NotImplementedError
