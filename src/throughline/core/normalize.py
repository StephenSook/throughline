"""Normalization.

Entity resolution across institutions fails or succeeds here. Two authorities
describing the same building write it as "929 CHARLES ALLEN DRIVE N. E." and
"929 Charles Allen Dr NE", and no amount of clever matching downstream recovers
from comparing those two strings literally.

Deliberately deterministic and dependency-light: every transformation below is
inspectable and testable, which matters because a match this system gets wrong
is a claim about a real place that we then report to a human as a defect.
"""

from __future__ import annotations

import re

# USPS Publication 28 suffix abbreviations, restricted to what actually appears
# in Atlanta municipal data. Expanding this blindly adds failure modes without
# adding matches.
_SUFFIX = {
    "STREET": "ST",
    "ST": "ST",
    "AVENUE": "AVE",
    "AVE": "AVE",
    "AV": "AVE",
    "ROAD": "RD",
    "RD": "RD",
    "DRIVE": "DR",
    "DR": "DR",
    "BOULEVARD": "BLVD",
    "BLVD": "BLVD",
    "PARKWAY": "PKWY",
    "PKWY": "PKWY",
    "PKY": "PKWY",
    "LANE": "LN",
    "LN": "LN",
    "PLACE": "PL",
    "PL": "PL",
    "COURT": "CT",
    "CT": "CT",
    "CIRCLE": "CIR",
    "CIR": "CIR",
    "TERRACE": "TER",
    "TER": "TER",
    "TRAIL": "TRL",
    "TRL": "TRL",
    "HIGHWAY": "HWY",
    "HWY": "HWY",
    "WAY": "WAY",
    "PLAZA": "PLZ",
    "PLZ": "PLZ",
    "SQUARE": "SQ",
    "SQ": "SQ",
    "CONNECTOR": "CONN",
    "EXTENSION": "EXT",
    "EXT": "EXT",
}

# Directionals. Atlanta is quadrant-addressed, so NW/NE/SW/SE is load-bearing:
# the same street number and name exists in more than one quadrant, and dropping
# the directional would merge two genuinely different places into one entity.
_DIRECTIONAL = {
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
    "N": "N",
    "S": "S",
    "E": "E",
    "W": "W",
    "NE": "NE",
    "NW": "NW",
    "SE": "SE",
    "SW": "SW",
}

_UNIT_NOISE = re.compile(
    r"\b(SUITE|STE|APT|APARTMENT|UNIT|BLDG|BUILDING|FLOOR|FL|RM|ROOM|#)\s*[\w-]*",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]")
_MULTISPACE = re.compile(r"\s+")

# Organisational boilerplate that differs between registries describing the same
# operator, e.g. "21ST CENTURY LEADERS INC." vs "21st Century Leaders".
_ORG_NOISE = {
    "INC",
    "INCORPORATED",
    "LLC",
    "L L C",
    "LTD",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "THE",
    "AND",
}


def normalize_address(raw: str | None) -> str:
    """Collapse an address to a comparable canonical form.

    Returns "" for anything unusable, including whitespace-only values. A blank
    address is itself a finding, so the caller must be able to distinguish it
    rather than have us silently substitute something plausible.
    """
    if not raw:
        return ""
    text = raw.upper().strip()
    if not text:
        return ""

    text = _UNIT_NOISE.sub(" ", text)
    # "N. E." -> "NE" before punctuation is stripped, or the two letters split.
    text = re.sub(r"\b([NSEW])\.\s*([NSEW])\.", r"\1\2", text)
    text = _NON_ALNUM.sub(" ", text)
    text = _MULTISPACE.sub(" ", text).strip()
    if not text:
        return ""

    tokens = text.split(" ")
    out: list[str] = []
    for i, tok in enumerate(tokens):
        # Only expand a directional at the head or tail; "WEST END AVE" has a
        # street named West, not a directional prefix.
        if tok in _DIRECTIONAL and (i == 0 or i >= len(tokens) - 2):
            out.append(_DIRECTIONAL[tok])
        elif tok in _SUFFIX:
            out.append(_SUFFIX[tok])
        else:
            out.append(tok)
    return " ".join(out)


def normalize_name(raw: str | None) -> str:
    """Collapse an organisation name to a comparable canonical form."""
    if not raw:
        return ""
    text = _NON_ALNUM.sub(" ", raw.upper())
    text = _MULTISPACE.sub(" ", text).strip()
    if not text:
        return ""
    tokens = [t for t in text.split(" ") if t not in _ORG_NOISE]
    return " ".join(tokens) if tokens else text


def normalize_zip(raw: str | int | None) -> str:
    """ZIP5. Returns "" when there is no usable ZIP at all."""
    if raw is None:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) < 5:
        return ""
    return digits[:5]


def blocking_key(name: str | None, zip_code: str | int | None) -> str:
    """Cheap key that puts plausible matches in the same bucket.

    Comparing all 681 facilities against all 506 licences is 344,586 pairs. We
    only ever score pairs that share a ZIP and a first name token, which is the
    difference between a pipeline that finishes inside a demo and one that does
    not. Recall cost is real but small: a facility whose ZIP disagrees across
    both sources is a divergence we catch through a different rule anyway.
    """
    n = normalize_name(name)
    z = normalize_zip(zip_code)
    head = n.split(" ")[0][:6] if n else ""
    return f"{z}|{head}"
