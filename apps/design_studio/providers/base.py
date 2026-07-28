"""The contract every design source implements.

Internal sources (catalogue, past orders, library) and external ones
(Pinterest, Google Images) are searched through the same interface, so adding a
platform later is a new provider registered in ``registry`` -- not a change to
the studio's search, ranking or gallery code.
"""

from dataclasses import dataclass, field, asdict
from decimal import Decimal


@dataclass
class DesignCandidate:
    """One design returned by a source, before ranking."""

    source: str
    source_ref: str
    title: str
    image_url: str
    source_url: str = ''
    designer: str = ''
    garment_type: str = ''
    occasion: str = ''
    attributes: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    colour_palette: list = field(default_factory=list)
    estimated_price: Decimal = Decimal('0')
    popularity: int = 0
    # Ranking fills these in; the source leaves them alone.
    match_score: int = 0
    match_reasons: list = field(default_factory=list)

    def to_dict(self):
        data = asdict(self)
        data['estimated_price'] = float(self.estimated_price or 0)
        return data


class DesignSourceProvider:
    key = ''
    label = ''
    is_external = False

    def available(self):
        """Whether this source can be searched right now.

        External providers return False until their credentials are configured,
        which is how the gallery reports a source as unavailable instead of
        failing the whole search.
        """
        return True

    def search(self, queries, context, limit=20):
        raise NotImplementedError
