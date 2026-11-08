Tiny divisors (below ~1e-80) now return a typed InvalidUncertainty error instead of raising a pydantic ValidationError or OverflowError.
