
import ast
import math
from decimal import Decimal, InvalidOperation

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

MAX_VALUE = 10 ** 9


class FormulaError(ValueError):
    pass


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
            if node.func.id == 'round' and len(args) > 1:
                args[1] = int(args[1])
            return _check(function(*args), f'{node.func.id}()')
        except (TypeError, ValueError, OverflowError) as exc:
            raise FormulaError(f"{node.func.id}() could not be evaluated: {exc}")

    raise FormulaError(
        f'{type(node).__name__} is not allowed in a formula.'
    )


def evaluate(expression, variables=None):
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
    try:
        tree = ast.parse(str(expression or ''), mode='eval')
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id not in FUNCTIONS}


_ALLOWED_NODES = (
    ast.Expression, ast.Constant, ast.Name, ast.Load,
    ast.UnaryOp, ast.USub, ast.UAdd, ast.Not,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.BoolOp, ast.And, ast.Or, ast.IfExp, ast.Call,
)


def validate_syntax(expression):
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
