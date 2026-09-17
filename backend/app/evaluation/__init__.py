"""Evaluation & quality engineering layer BizIntel AI (Phase 5).

Paket DETERMINISTIK (bukan LLM-as-a-judge):
- cases.py   : dataset evaluasi (schema + loader)
- numerics.py: parser angka multi-format + pencocokan toleransi
- metrics.py : evaluator tool-selection, hit@k, citation, groundedness, dll.
- runner.py  : orchestration (mode deterministik & live) + report JSON

Lihat docs/agent-phase5.md.
"""
