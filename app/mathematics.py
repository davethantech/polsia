"""Verified bounded Decimal arithmetic; never evaluate arbitrary Python syntax."""
import ast
from decimal import Decimal, localcontext, InvalidOperation, DivisionByZero

MAX_EXPRESSION=240
MAX_DIGITS=60


def evaluate(expression):
    if not isinstance(expression,str) or len(expression)>MAX_EXPRESSION:
        raise ValueError('Expression too long')
    try: parsed=ast.parse(expression,mode='eval')
    except SyntaxError:raise ValueError('Invalid expression') from None
    def calc(node,depth=0):
        if depth>18:raise ValueError('Expression too deep')
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            # Parse textual numeric literal to avoid binary floating-point artifacts.
            s=ast.get_source_segment(expression,node)
            if not s or len(s)>MAX_DIGITS:raise ValueError('Numeric literal too long')
            return Decimal(s.replace('_',''))
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            v=calc(node.operand,depth+1);return v if isinstance(node.op,ast.UAdd) else -v
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a=calc(node.left,depth+1);b=calc(node.right,depth+1)
            if isinstance(node.op,ast.Add):return a+b
            if isinstance(node.op,ast.Sub):return a-b
            if isinstance(node.op,ast.Mult):return a*b
            if b==0:raise ValueError('Division by zero')
            return a/b
        raise ValueError('Disallowed mathematical operation')
    try:
        with localcontext() as ctx:
            ctx.prec=48
            value=calc(parsed.body)
            if not value.is_finite() or abs(value.adjusted())>100:raise ValueError('Result magnitude too large')
            return {'value':format(value,'f'),'method':'decimal_ast','precision_digits':ctx.prec,'verified':'computed_not_proven'}
    except (InvalidOperation,DivisionByZero,OverflowError) as e:
        raise ValueError('Numeric operation failed') from e
