"""全ドキュメントの生成と検証."""

from dit.docs.guide import generate_guide
from dit.docs.reference import generate_reference
from dit.docs.validate import validate_docs


def main() -> None:
    """リファレンスとガイドを生成し、サイト全体を検証する."""
    generate_reference()
    generate_guide()
    validate_docs()
