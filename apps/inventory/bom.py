"""Working out what a garment needs.

A BOM line says "0.15 * bust metres of lining, plus 8% waste". This turns that,
plus a particular garment's measurements, into a number and a unit that stock
can actually be reserved against.

The order of operations matters and is deliberate:

    quantity  ->  formula or fixed amount
              ->  waste allowance added
              ->  converted into the stocked item's unit

Waste is applied before conversion, not after, so a percentage always means the
same thing regardless of which unit the line happens to be written in. Doing it
the other way round gives different answers for the same recipe depending on
whether someone wrote 1 roll or 50 metres.
"""

from decimal import Decimal, InvalidOperation, Overflow, ROUND_HALF_UP

from .formula import FormulaError, evaluate
from .models import GLOBAL_UNIT_CONVERSIONS, BomLine, UnitConversion

#: Quantities are stored to three decimal places; rounding here rather than
#: leaving a long float keeps the reservation and the ledger line identical.
PRECISION = Decimal('0.001')


class BomError(ValueError):
    """A BOM that cannot be turned into a requirement."""


def _quantise(value):
    """Round to the stored precision, reporting a value too big to store.

    decimal.InvalidOperation is an ArithmeticError, not a ValueError, so an
    unquantisable value used to travel straight past every `except ValueError`
    in the stack and out as a 500.
    """
    try:
        return Decimal(value).quantize(PRECISION, rounding=ROUND_HALF_UP)
    except (InvalidOperation, Overflow, ValueError):
        raise BomError(f'{value} is too large to be a usable quantity.')


def convert(quantity, from_unit, to_unit, item=None, *, quantise=True):
    """Convert `quantity` between units, using the item's own factors first.

    Returns None when there is no known conversion, which the caller reports
    rather than guessing -- silently treating 2 rolls as 2 metres would put the
    wrong number into a reservation and nobody would see it until the fabric ran
    out.
    """
    def finish(value):
        return _quantise(value) if quantise else Decimal(value)

    if from_unit == to_unit:
        return finish(quantity)

    if item is not None:
        row = UnitConversion.objects.filter(
            item=item, from_unit=from_unit, to_unit=to_unit).first()
        if row is not None:
            return finish(Decimal(quantity) * row.factor)
        # A factor given one way also holds the other way.
        inverse = UnitConversion.objects.filter(
            item=item, from_unit=to_unit, to_unit=from_unit).first()
        if inverse is not None and inverse.factor != 0:
            return finish(Decimal(quantity) / inverse.factor)

    factor = GLOBAL_UNIT_CONVERSIONS.get((from_unit, to_unit))
    if factor is not None:
        return finish(Decimal(quantity) * factor)
    return None


def line_requirement(line, variables=None, *, include_optional=False):
    """What one BOM line needs, as a dict. Returns None if the line is skipped."""
    if line.is_optional and not include_optional:
        return None

    if line.quantity_formula:
        try:
            base = evaluate(line.quantity_formula, variables or {})
        except FormulaError as exc:
            raise BomError(f"{line.material_name}: {exc}")
        if base < 0:
            raise BomError(
                f"{line.material_name}: formula produced {base}, which is negative.")
    else:
        base = Decimal(line.quantity)

    with_waste = base * (Decimal('1') + (Decimal(line.waste_percent) / Decimal('100')))

    item = line.inventory_item
    unit = line.unit
    conversion_note = None

    # A line may be written in a different unit from the one the item is stocked
    # in -- "2 rolls" of something held in metres. Reservation happens in the
    # stocked unit, so the line has to be brought into it.
    # Converted from the UNROUNDED figure. Rounding to 3dp in the line's unit
    # first and converting afterwards multiplies that rounding error by the
    # conversion factor -- with a factor of 50, half a thousandth of a roll
    # becomes 25 thousandths of a metre.
    if item is not None and item.unit != line.unit:
        result = convert(with_waste, line.unit, item.unit, item=item, quantise=False)
        if result is None:
            raise BomError(
                f"{line.material_name}: no conversion from {line.get_unit_display()} to "
                f"{item.get_unit_display()}. Add one on the item before using this BOM."
            )
        conversion_note = (
            f"{_quantise(with_waste)} {line.unit} -> {_quantise(result)} {item.unit}")
        with_waste = result
        unit = item.unit

    converted = _quantise(with_waste)

    return {
        'line_id': str(line.id),
        'role': line.role,
        'material': line.material_name,
        'inventory_item_id': str(item.id) if item else None,
        'catalog_item_id': str(line.catalog_item_id) if line.catalog_item_id else None,
        'base_quantity': _quantise(base),
        'base_unit': line.unit,
        'waste_percent': Decimal(line.waste_percent),
        'required_quantity': converted,
        'unit': unit,
        'is_optional': line.is_optional,
        'is_customer_supplied': line.is_customer_supplied,
        'conversion': conversion_note,
    }


def requirements(bom, variables=None, *, include_optional=False):
    """Everything `bom` needs for one garment.

    Customer-supplied lines are returned but flagged. They are part of the
    recipe -- the garment cannot be made without them -- but they are never
    reserved from boutique stock, which is the rule stage 4 enforces.
    """
    lines = (BomLine.objects.filter(bom=bom)
             .select_related('inventory_item', 'catalog_item')
             .order_by('sequence', 'role'))
    out = []
    for line in lines:
        requirement = line_requirement(
            line, variables, include_optional=include_optional)
        if requirement is not None:
            out.append(requirement)
    return out


def summarise(bom, variables=None, *, include_optional=False):
    """Requirements plus the totals a caller usually wants alongside them."""
    rows = requirements(bom, variables, include_optional=include_optional)
    boutique = [r for r in rows if not r['is_customer_supplied']]
    customer = [r for r in rows if r['is_customer_supplied']]
    return {
        'bom': str(bom.id),
        'name': bom.name,
        'version': bom.version,
        'requirements': rows,
        'boutique_line_count': len(boutique),
        'customer_supplied_line_count': len(customer),
        'unresolved_line_count': sum(
            1 for r in boutique if r['inventory_item_id'] is None),
    }
