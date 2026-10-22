"""The engineering domains (knowledge areas) a document can be classified into.

Single source of truth: the API validates against it, the UI renders it, every chunk in Qdrant
carries the document's domain id in its payload (`domain`) so chat can be scoped to one domain.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

UNASSIGNED = "unassigned"


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    description: str
    keywords: tuple[str, ...]  # offline classification hints (lower case)


DOMAINS: tuple[Domain, ...] = (
    Domain("adas", "ADAS",
           "Advanced driver-assistance systems: ultrasonic / radar / camera sensors, parking (PDC), sensor mounting "
           "and integration, FMEAs and control plans for ADAS components.",
           ("adas", "ultrasonic", "uss", "pdc", "radar", "sensor", "lidar", "camera", "parking", "fmea",
            "control plan", "field of view", "fov", "decoupling ring")),
    Domain("benchmarking", "Benchmarking",
           "Competitor vehicle teardown and benchmarking data: part materials, weights, thickness, manufacturing "
           "processes and design solutions compared across OEM vehicles.",
           ("benchmark", "vehicle / model", "competitor", "teardown", "oem", "mercedes", "bmw", "audi", "porsche",
            "toyota", "cadillac", "volvo")),
    Domain("eds", "EDS",
           "Engineering Design Services design guidelines: body exterior / interior part design rules, carbon fiber, "
           "bonnet, frunk, grille, heating elements, packaging, assembly and manufacturing guidelines.",
           ("eds", "design guideline", "guideline", "bonnet", "frunk", "carbon fiber", "carbon fibre", "grille",
            "heating element", "radome", "design rule", "packaging")),
    Domain("lead-engineering", "Lead Engineering",
           "Lead engineer knowledge: issue logs, lessons learned, Q&A, release processes (3DX, iCreate, UBOM, "
           "CA/CO), APQP, PPIR and programme management know-how.",
           ("lead engineer", "grooming", "lessons learn", "issue", "q&a", "3dx", "icreate", "ubom", "apqp",
            "release", "ppir", "aims")),
    Domain("materials-net", "Materials Net",
           "Materials knowledge: polymers, metals and composites, grades and specifications, mechanical properties, "
           "material selection and standards.",
           ("material", "polymer", "polypropylene", "pp-", "pa6", "abs", "aluminium", "aluminum", "steel",
            "magnesium", "composite", "grade", "tensile", "density", "resin")),
    Domain("supplier-database", "Supplier Database",
           "Supplier information: supplier capabilities, contacts, locations, quality ratings, commodities and "
           "sourcing data.",
           ("supplier", "vendor", "sourcing", "commodity", "tier 1", "tier-1", "procurement", "capability",
            "quality rating")),
)

DOMAIN_IDS = {d.id for d in DOMAINS}
VALID_DOMAIN_IDS = DOMAIN_IDS | {UNASSIGNED}


def validate_domain(domain: str | None) -> str:
    value = (domain or UNASSIGNED).strip().lower()
    if value not in VALID_DOMAIN_IDS:
        raise ValueError(f"Unknown domain '{domain}'. Valid: {sorted(VALID_DOMAIN_IDS)}")
    return value


def domains_payload() -> list[dict]:
    return [{k: v for k, v in asdict(d).items() if k != "keywords"} for d in DOMAINS]
