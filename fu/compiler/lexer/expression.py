from dataclasses import dataclass
from typing import Iterable, Union

from .. import TokenStream

from . import Lex
from .operator import Operator
from .atom import Atom


@dataclass(repr=False, slots=True, frozen=True)
class Expression(Lex):
    """Expression := Operator | Atom;"""
    value: Union[Operator, 'Atom']

    # def __repr__(self) -> str:
    #     return f"Expression<{self.value!r}>"

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        for t in (Operator, Atom):
            if (ret := t.try_lex(stream)) is not None:
                return ret
