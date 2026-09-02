"""Glyphs protocol and the six sub-cell packing strategies.

Codepoint tables for OCTANT and SEXTANT were derived from the Unicode 16.0 NamesList
(https://www.unicode.org/Public/16.0.0/ucd/NamesList.txt), parsing every `BLOCK OCTANT-N`
and `BLOCK SEXTANT-N` name into its bit pattern, then filling the patterns that already
had a codepoint elsewhere (space, full block, halves, quadrants, diagonals, and four
corner and two mid-column patterns from the Legacy Computing Supplement) by hand,
cross-checked against the Block Elements and Symbols for Legacy Computing charts.
"""

from __future__ import annotations

from typing import ClassVar

from _generated_maps import OCTANT_MAP, SEXTANT_MAP
from beartype.typing import Protocol


class Glyphs(Protocol):
    """Packs a sub-cell bit block into a single terminal character."""

    rows: int
    cols: int
    name: str

    def to_char(self, bits: int) -> str:
        """Render the lit sub-cells (bit i set = sub-cell i, row-major) as one glyph."""


class BlockGlyphs:
    rows, cols, name = 1, 1, 'BLOCK'

    def to_char(self, bits: int) -> str:
        return '█' if bits & 1 else ' '


class HalfBlockGlyphs:
    rows, cols, name = 2, 1, 'HALFBLOCK'
    _CHARS: ClassVar = {0b00: ' ', 0b10: '▀', 0b01: '▄', 0b11: '█'}

    def to_char(self, bits: int) -> str:
        return self._CHARS[bits]


class QuadrantGlyphs:
    rows, cols, name = 2, 2, 'QUADRANT'
    _CHARS: ClassVar = {
        0b0000: ' ',
        0b0001: '▘',
        0b0010: '▝',
        0b0011: '▀',
        0b0100: '▖',
        0b0101: '▌',
        0b0110: '▞',
        0b0111: '▛',
        0b1000: '▗',
        0b1001: '▚',
        0b1010: '▐',
        0b1011: '▜',
        0b1100: '▄',
        0b1101: '▙',
        0b1110: '▟',
        0b1111: '█',
    }

    def to_char(self, bits: int) -> str:
        return self._CHARS[bits]


class SextantGlyphs:
    rows, cols, name = 3, 2, 'SEXTANT'

    def to_char(self, bits: int) -> str:
        return chr(SEXTANT_MAP[bits])


class OctantGlyphs:
    rows, cols, name = 4, 2, 'OCTANT'

    def to_char(self, bits: int) -> str:
        return chr(OCTANT_MAP[bits])


class BrailleGlyphs:
    rows, cols, name = 4, 2, 'BRAILLE'
    _BRAILLE_BIT = (0, 3, 1, 4, 2, 5, 6, 7)  # canonical row-major index -> braille dot bit

    def to_char(self, bits: int) -> str:
        out = 0
        for i, dot in enumerate(self._BRAILLE_BIT):
            if bits & (1 << i):
                out |= 1 << dot
        return chr(0x2800 + out)


GLYPHS: dict[str, Glyphs] = {
    'BLOCK': BlockGlyphs(),
    'HALFBLOCK': HalfBlockGlyphs(),
    'QUADRANT': QuadrantGlyphs(),
    'SEXTANT': SextantGlyphs(),
    'OCTANT': OctantGlyphs(),
    'BRAILLE': BrailleGlyphs(),
}
