"""Golden dataset formalizado e versionado."""

from src.evaluation.golden.loader import (
    GoldenDataset,
    load_expansion_dataset,
    load_golden_dataset,
)

__all__ = ["GoldenDataset", "load_expansion_dataset", "load_golden_dataset"]
