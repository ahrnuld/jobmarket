"""Data pipeline for the HBO-ICT job market insights website.

Stages (see docs/ARCHITECTURE.md):
    ingest -> clean/deduplicate -> classify -> aggregate -> validate -> publish
"""

__version__ = "0.1.0"
