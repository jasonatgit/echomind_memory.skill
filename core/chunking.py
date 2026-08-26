# EchoMind — text chunking for ingestion paths
# Absorbed from AEIS knowledge._chunk_text: fenced code blocks (```...```) are
# protected as whole blocks (inner blank lines never split them); over-long
# blocks are sliced in line groups, preserving order, never mid-line.

import re
from typing import List

MAX_CHUNK = 1500


def _split_long(block: str, max_len: int) -> List[str]:
    """Slice an over-long block, preferring blank-line paragraphs then line groups."""
    if len(block) <= max_len:
        return [block]

    out: List[str] = []
    cur = ""
    for para in re.split(r"\n\s*\n", block):
        if len(cur) + len(para) + 2 > max_len and cur:
            out.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)

    final: List[str] = []
    for piece in out:
        if len(piece) <= max_len:
            final.append(piece)
            continue
        buf, lines = "", piece.splitlines()
        for ln in lines:
            if len(buf) + len(ln) + 1 > max_len and buf:
                final.append(buf)
                buf = ln
            else:
                buf = f"{buf}\n{ln}" if buf else ln
        if buf:
            final.append(buf)
    return final


def chunk_text(text: str, max_len: int = MAX_CHUNK) -> List[str]:
    """Split *text* into chunks of at most *max_len* chars.

    Fenced code blocks (``` ... ```) are extracted whole and never split on
    their inner blank lines (the AEIS bug: plain blank-line splitting cut code
    blocks in half). Over-long code blocks are sliced in line groups, keeping
    order and never breaking a line mid-way.
    """
    if not text:
        return []
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    chunks: List[str] = []
    for part in re.split(r"(```[\s\S]*?```)", text):
        if not part:
            continue
        if part.startswith("```") and part.endswith("```"):
            chunks.extend(_split_long(part, max_len))
        else:
            chunks.extend(_split_long(part, max_len))
    return [c for c in chunks if c and c.strip()]
