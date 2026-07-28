"""Deterministic design intelligence.

Scores are a weighted sum of signals the CRM already holds, normalised to a
0-100 confidence. Two properties matter more than cleverness here: the same
context and the same candidate always produce the same score, and every point
awarded comes with the human-readable reason that earned it -- the gallery
shows those reasons verbatim, so an owner can tell a customer why a design was
suggested.
"""

from decimal import Decimal

from .base import DesignIntelligence

# Weight, and the reason shown when the signal fires. Weights total 100.
WEIGHTS = {
    'garment': 25,
    'occasion': 18,
    'style': 20,
    'colour': 12,
    'budget': 10,
    'popularity': 10,
    'history': 5,
}

_QUALITY_WORDS = {
    'Bridal': ['Luxury', 'Designer', 'Traditional'],
    'Wedding': ['Luxury', 'Designer', 'Traditional'],
    'Reception': ['Designer', 'Contemporary'],
    'Party': ['Contemporary', 'Designer'],
    'Festive': ['Traditional', 'Festive Wear'],
    'Casual': ['Everyday', 'Minimal'],
}


def _clean(value):
    return str(value or '').strip()


def _lower_set(values):
    return {str(v).strip().lower() for v in values if str(v).strip()}


class RuleBasedIntelligence(DesignIntelligence):
    key = 'rules'

    # -- Query generation ------------------------------------------------

    def generate_queries(self, context, extra_keywords=None):
        garment = _clean(context.garment_type) or 'Outfit'
        occasion = _clean(context.occasion)
        colour = context.favourite_colours[0] if context.favourite_colours else ''
        embellishment = _clean(context.style_preferences.get('embellishments'))
        pattern = _clean(context.style_preferences.get('pattern'))

        queries = []

        def add(*parts):
            query = ' '.join(p for p in parts if p).strip()
            if query and query not in queries:
                queries.append(query)

        add(occasion, colour, garment)
        for qualifier in _QUALITY_WORDS.get(occasion, ['Designer']):
            add(qualifier, garment)
        add(embellishment, garment)
        add(pattern, garment)
        add(context.gender, garment, occasion)
        add(garment)

        for keyword in (extra_keywords or []):
            add(_clean(keyword))

        return queries[:8]

    # -- Ranking ---------------------------------------------------------

    def rank(self, candidates, context):
        scored = [(candidate, *self._score(candidate, context)) for candidate in candidates]

        # A signal no design in the result set could possibly supply must not
        # drag every score down. Boutique catalogue rows carry no occasion, so
        # scoring against the full 100 would cap a perfect catalogue match in
        # the forties and make the whole gallery look like a poor fit. The
        # denominator is therefore the weight that was actually in play.
        in_play = set()
        for _, points, _ in scored:
            in_play.update(points.keys())
        attainable = sum(WEIGHTS[signal] for signal in in_play) or sum(WEIGHTS.values())

        ranked = []
        for candidate, points, reasons in scored:
            earned = sum(points.values())
            candidate.match_score = max(0, min(100, round(100 * earned / attainable)))
            candidate.match_reasons = reasons
            ranked.append(candidate)

        # source_ref breaks ties so equal-scoring designs keep a stable order
        # between identical searches.
        ranked.sort(key=lambda c: (-c.match_score, c.source, c.source_ref))
        return ranked

    def _score(self, candidate, context):
        """Return the points earned per signal, and the reasons behind them.

        A signal only appears in the returned mapping when it was evaluable for
        this candidate -- that is what lets ``rank`` tell "scored zero" apart
        from "could not be judged".
        """
        points = {}
        reasons = []
        attributes = candidate.attributes or {}

        if context.garment_type:
            points['garment'] = 0
            if _clean(candidate.garment_type).lower() == context.garment_type.lower():
                points['garment'] = WEIGHTS['garment']
                reasons.append(f"Matches the {context.garment_type} being ordered")

        if context.occasion:
            haystack = _lower_set([candidate.occasion, *candidate.tags, candidate.title])
            if any(context.occasion.lower() in value for value in haystack):
                points['occasion'] = WEIGHTS['occasion']
                reasons.append(f"Suited to a {context.occasion} occasion")
            elif candidate.occasion:
                # The design states an occasion and it is not this one, so this
                # is a real miss. A design that simply never declares an
                # occasion is unjudged rather than wrong -- most catalogue rows
                # carry no occasion at all.
                points['occasion'] = 0

        style_hits, comparable = self._style_hits(attributes, context)
        if comparable:
            points['style'] = int(WEIGHTS['style'] * len(style_hits) / comparable)
            if style_hits:
                reasons.append("Matches preferred " + ", ".join(style_hits))

        if context.favourite_colours:
            colour_hit = self._colour_hit(candidate, context)
            points['colour'] = WEIGHTS['colour'] if colour_hit else 0
            if colour_hit:
                reasons.append(f"Matches preferred colour palette ({colour_hit})")

        if context.budget and candidate.estimated_price:
            within = self._within_budget(candidate, context)
            points['budget'] = WEIGHTS['budget'] if within else 0
            if within:
                reasons.append(f"Within the ₹{Decimal(context.budget):,.0f} budget")

        if candidate.popularity:
            if candidate.popularity >= 70:
                points['popularity'] = WEIGHTS['popularity']
                reasons.append("Boutique best seller")
            else:
                points['popularity'] = WEIGHTS['popularity'] // 2 if candidate.popularity >= 40 else 0

        if context.previous_order_count:
            points['history'] = WEIGHTS['history'] if candidate.source == 'past_order' else 0
            if candidate.source == 'past_order':
                reasons.append("Similar to a previously stitched garment")

        if context.body_type and context.body_type.lower() in _lower_set(candidate.tags):
            reasons.append(f"Suitable for {context.body_type} measurements")

        return points, reasons

    def _style_hits(self, attributes, context):
        """Matched preferences, and how many could be compared at all.

        Scoring hits against a fixed denominator punished designs for
        attributes their source simply does not record. Only pairs where both
        the customer stated a preference and the design declares the attribute
        count towards the total.
        """
        hits = []
        comparable = 0
        pairs = [
            ('neck_type', 'neckline'),
            ('sleeve', 'sleeve'),
            ('back', 'back'),
            ('pattern', 'pattern'),
            ('embroidery', 'embellishments'),
            ('fit', 'silhouette'),
        ]
        for attribute_key, preference_key in pairs:
            preferred = _clean(context.style_preferences.get(preference_key)).lower()
            actual = _clean(attributes.get(attribute_key)).lower()
            if not preferred or not actual:
                continue
            comparable += 1
            if preferred in actual or actual in preferred:
                hits.append(preference_key)
        return hits, comparable

    def _colour_hit(self, candidate, context):
        if not context.favourite_colours:
            return ''
        haystack = _lower_set([*candidate.colour_palette, *candidate.tags, candidate.title])
        for colour in context.favourite_colours:
            needle = colour.lower()
            if any(needle in value for value in haystack):
                return colour
        return ''

    def _within_budget(self, candidate, context):
        # An unpriced reference is not evidence against it, which is why the
        # caller only evaluates this signal when a price exists.
        budget = Decimal(context.budget or 0)
        price = Decimal(candidate.estimated_price or 0)
        return budget > 0 and 0 < price <= budget

    # -- Attribute extraction --------------------------------------------

    def analyse(self, candidate, context=None):
        """Fill the structured attribute set, inferring what is missing.

        Internal sources already carry most of these fields. What is absent is
        inferred from the design's own tags and title -- never from the
        customer's preferences, which would make every design look like a
        perfect match for the person it is being shown to.
        """
        attributes = {
            'neck_type': '', 'sleeve': '', 'fabric': '', 'embroidery': '',
            'occasion': '', 'colour': '', 'fit': '', 'pattern': '',
        }
        attributes.update({k: v for k, v in (candidate.attributes or {}).items() if v})

        if not attributes['occasion']:
            attributes['occasion'] = _clean(candidate.occasion)
        if not attributes['colour'] and candidate.colour_palette:
            attributes['colour'] = _clean(candidate.colour_palette[0])

        vocabulary = {
            'neck_type': ['boat neck', 'v-neck', 'sweetheart', 'round neck', 'collar', 'halter'],
            'sleeve': ['sleeveless', 'full sleeve', 'half sleeve', 'cap sleeve', 'puff sleeve', 'bell sleeve'],
            'fabric': ['silk', 'georgette', 'chiffon', 'cotton', 'velvet', 'crepe', 'organza', 'satin', 'net'],
            'embroidery': ['zari', 'zardozi', 'sequin', 'mirror work', 'thread work', 'stone work', 'aari'],
            'fit': ['regular', 'slim', 'relaxed', 'a-line', 'flared', 'straight'],
            'pattern': ['traditional', 'contemporary', 'floral', 'geometric', 'minimal', 'ethnic'],
        }
        haystack = ' '.join([candidate.title or '', ' '.join(str(t) for t in candidate.tags or [])]).lower()
        for key, terms in vocabulary.items():
            if attributes[key]:
                continue
            for term in terms:
                if term in haystack:
                    attributes[key] = term.title()
                    break

        return attributes
