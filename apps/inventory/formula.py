"""Evaluating a BOM line's quantity formula.

A formula is a small arithmetic expression over a garment's own measurements,
written by the boutique: ``0.15 * bust + 0.4`` for a lining, or
``2.2 if length > 42 else 1.9`` for a skirt panel.

This is emphatically **not** eval(). A formula arrives from the database, which
means it arrives from whoever could write to it, and eval() on that is arbitrary
code execution against the server. Instead the expression is parsed to an AST and
walked with an explicit allow-list of node types: arithmetic, comparison, a
conditional, numeric literals and named variables. Anything else -- an attribute
access, a subscript, a lambda, a comprehension, a call to anything outside the
four whitelisted functions -- is refused by the walker rather than by a blacklist,
so a construct nobody thought of is rejected by default instead of slipping
through.

Two further limits stop a formula that is syntactically harmless from hanging the
process: the expression length is capped, and exponents are bounded, because
``9**9**9`` is a denial of service written in four characters.
"""

import ast
import math
from decimal import Decimal, InvalidOperation

#: The only callables a formula may use.
FUNCTIONS = {
    'min': min,
    'max': max,
    'round': round,
    'abs': abs,
    'ceil': math.ceil,
    'floor': math.floor,
}

MAX_LENGTH = 500
MAX_EXPONENT = 8

#: Every intermediate value is bounded, not just the exponent. Bounding the
#: exponent alone is not enough -- ((9**8)**8)**8 keeps each exponent at 8 and
#: still overflows, and a caller-supplied measurement can be astronomical on its
#: own. The ceiling matches what a quantity can actually be stored as: quantities
#: are DecimalField(max_digits=12, decimal_places=3), so anything at or above
#: 10**9 cannot be saved anyway and is better refused here, where the message can
#: say which formula did it, than in the database.
MAX_VALUE = 10 ** 9


class FormulaError(ValueError):
    """A formula that cannot be parsed, or asks for something it may not have."""


_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}

_COMPARE_OPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


def _check(value, where):
    """Every value that flows through the evaluator passes through here.

    Guarding only the final result is not enough: an intermediate can be
    infinite, complex or astronomically large and then blow up somewhere with no
    context -- ``(-1) ** 0.5`` is a complex number, ``round(1, 1e400)`` is an
    OverflowError, and a merely enormous float reaches the caller and raises
    decimal.InvalidOperation when it is quantised. Catching all of it at one
    choke point turns every one of those into a FormulaError that names the
    formula instead of a 500.
    """
    if isinstance(value, complex):
        raise FormulaError(
            f'{where} produced a complex number. A negative base cannot be '
            f'raised to a fractional power.'
        )
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise FormulaError(f'{where} produced {value!r}, which is not a number.')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise FormulaError(f'{where} produced a value too large to use.')
    if result != result:
        raise FormulaError(f'{where} produced "not a number".')
    if result in (float('inf'), float('-inf')):
        raise FormulaError(f'{where} produced an infinite value.')
    if abs(result) > MAX_VALUE:
        raise FormulaError(
            f'{where} produced {result:.6g}, which is beyond the largest usable '
            f'quantity ({MAX_VALUE:,}).'
        )
    return result


def _number(value, where):
    """Coerce a variable's value to a float the arithmetic can use.

    Variables come from the request body, so "nan" and "1e999" arrive as strings
    that float() accepts happily. _check is what stops them.
    """
    if isinstance(value, bool):
        raise FormulaError(f"'{where}' is {value!r}; measurements must be numbers.")
    if isinstance(value, (int, float, Decimal)):
        return _check(value, f"'{where}'")
    try:
        parsed = float(str(value))
    except (TypeError, ValueError, OverflowError):
        raise FormulaError(f"'{where}' is {value!r}, which is not a number.")
    return _check(parsed, f"'{where}'")


def _eval(node, variables):
    if isinstance(node, ast.Expression):
        return _eval(node.body, variables)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FormulaError(f'Only numbers are allowed in a formula, not {node.value!r}.')
        return _check(node.value, 'A literal in the formula')

    if isinstance(node, ast.Name):
        if node.id in variables:
            return _number(variables[node.id], node.id)
        raise FormulaError(
            f"Formula refers to '{node.id}', which is not one of the available "
            f"measurements ({', '.join(sorted(variables)) or 'none'})."
        )

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_eval(node.operand, variables)
        if isinstance(node.op, ast.UAdd):
            return +_eval(node.operand, variables)
        if isinstance(node.op, ast.Not):
            return float(not _eval(node.operand, variables))
        raise FormulaError('Unsupported unary operator in formula.')

    if isinstance(node, ast.BinOp):
        handler = _BIN_OPS.get(type(node.op))
        if handler is None:
            raise FormulaError('Unsupported operator in formula.')
        left = _eval(node.left, variables)
        right = _eval(node.right, variables)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise FormulaError(f'Exponents above {MAX_EXPONENT} are not allowed.')
        if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
            raise FormulaError('Formula divides by zero.')
        try:
            result = handler(left, right)
        except (OverflowError, ValueError, ZeroDivisionError) as exc:
            raise FormulaError(f'Formula could not be evaluated: {exc}')
        return _check(result, 'An operation in the formula')

    if isinstance(node, ast.Compare):
        # Chained comparisons (a < b < c) evaluate left to right, like Python.
        left = _eval(node.left, variables)
        for op, comparator in zip(node.ops, node.comparators):
            handler = _COMPARE_OPS.get(type(op))
            if handler is None:
                raise FormulaError('Unsupported comparison in formula.')
            right = _eval(comparator, variables)
            if not handler(left, right):
                return 0.0
            left = right
        return 1.0

    if isinstance(node, ast.BoolOp):
        # Python's own semantics: short-circuit, and yield the operand that
        # decided the result rather than collapsing to 1.0/0.0 after evaluating
        # everything. `waist or 30` should be the waist measurement when there
        # is one, not "true".
        if isinstance(node.op, ast.And):
            result = 1.0
            for operand in node.values:
                result = _eval(operand, variables)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result = 0.0
            for operand in node.values:
                result = _eval(operand, variables)
                if result:
                    return result
            return result
        raise FormulaError('Unsupported boolean operator in formula.')

    if isinstance(node, ast.IfExp):
        return (_eval(node.body, variables) if _eval(node.test, variables)
                else _eval(node.orelse, variables))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError('Only plain function calls are allowed in a formula.')
        function = FUNCTIONS.get(node.func.id)
        if function is None:
            raise FormulaError(
                f"'{node.func.id}' is not available in a formula "
                f"(allowed: {', '.join(sorted(FUNCTIONS))})."
            )
        if node.keywords:
            raise FormulaError('Formula functions do not take keyword arguments.')

        args = [_eval(a, variables) for a in node.args]
        try:
            # round()'s second argument must be an int -- round(2.345, 2.0) is a
            # TypeError. Coerced inside the try, because int(inf) raises
            # OverflowError and doing this above the try was itself a route to a
            # 500 for round(1.5, 1e400).
            if node.func.id == 'round' and len(args) > 1:
                args[1] = int(args[1])
            return _check(function(*args), f'{node.func.id}()')
        except (TypeError, ValueError, OverflowError) as exc:
            # Wrong arity, or a value the function cannot take. Reported as a
            # formula problem rather than escaping as a 500.
            raise FormulaError(f"{node.func.id}() could not be evaluated: {exc}")

    raise FormulaError(
        f'{type(node).__name__} is not allowed in a formula.'
    )


def evaluate(expression, variables=None):
    """Evaluate `expression` against `variables`, returning a Decimal.

    Raises FormulaError for anything that is not a well-formed, permitted
    arithmetic expression over the variables provided.
    """
    if expression is None or not str(expression).strip():
        raise FormulaError('Formula is empty.')
    text = str(expression).strip()
    if len(text) > MAX_LENGTH:
        raise FormulaError(f'Formula is longer than {MAX_LENGTH} characters.')

    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError as exc:
        raise FormulaError(f'Formula is not valid: {exc.msg}.')

    result = _eval(tree, variables or {})
    if result != result or result in (float('inf'), float('-inf')):   # NaN / inf
        raise FormulaError('Formula did not produce a usable number.')
    try:
        return Decimal(str(round(result, 6)))
    except InvalidOperation:
        raise FormulaError('Formula did not produce a usable number.')


def variables_used(expression):
    """Every variable name a formula reads, for validating it against a garment."""
    try:
        tree = ast.parse(str(expression or ''), mode='eval')
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id not in FUNCTIONS}


#: Node types a formula may contain. Kept beside _eval deliberately: the two
#: must agree, and a construct added to one without the other is a bug.
_ALLOWED_NODES = (
    ast.Expression, ast.Constant, ast.Name, ast.Load,
    ast.UnaryOp, ast.USub, ast.UAdd, ast.Not,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.BoolOp, ast.And, ast.Or, ast.IfExp, ast.Call,
)


def validate_syntax(expression):
    """Check a formula is well-formed and permitted, WITHOUT evaluating it.

    Write-time validation cannot simply call evaluate(): the variables are the
    garment's measurements, which do not exist until an order does, so every
    real formula raises "unknown variable" at that point. Discriminating on that
    error *message* is what an earlier version did, and it was a hole -- _eval
    walks depth-first, so `hips * __import__('os')` raises the unknown-variable
    error from the left operand before it ever reaches the call on the right,
    and the hostile half was never examined.

    This walks the whole tree structurally instead, so every node is inspected
    regardless of evaluation order, and unbound names are simply allowed.
    """
    if expression is None or not str(expression).strip():
        raise FormulaError('Formula is empty.')
    text = str(expression).strip()
    if len(text) > MAX_LENGTH:
        raise FormulaError(f'Formula is longer than {MAX_LENGTH} characters.')

    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError as exc:
        raise FormulaError(f'Formula is not valid: {exc.msg}.')

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(f'{type(node).__name__} is not allowed in a formula.')
        if isinstance(node, ast.Constant) and (
            isinstance(node.value, bool) or not isinstance(node.value, (int, float))
        ):
            raise FormulaError(
                f'Only numbers are allowed in a formula, not {node.value!r}.')
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                name = getattr(node.func, 'id', type(node.func).__name__)
                raise FormulaError(
                    f"'{name}' is not available in a formula "
                    f"(allowed: {', '.join(sorted(FUNCTIONS))})."
                )
            if node.keywords:
                raise FormulaError('Formula functions do not take keyword arguments.')
    return True
