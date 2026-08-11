"""Generate and validate all documentation."""

from dit.docs.guide import generate_guide
from dit.docs.reference import generate_reference
from dit.docs.validate import validate_docs


def main() -> None:
    """Generate reference and guide pages, then validate the complete site."""
    generate_reference()
    generate_guide()
    validate_docs()
