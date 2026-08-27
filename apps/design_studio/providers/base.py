
from dataclasses import dataclass, field, asdict
from decimal import Decimal


@dataclass
class DesignCandidate:

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
        return True

    def search(self, queries, context, limit=20):
        raise NotImplementedError
