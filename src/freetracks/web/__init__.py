"""Web layer — a thin FastAPI backend wrapping the freetracks SearchEngine.

Run locally with: ``ftf serve`` (or ``uvicorn freetracks.web.app:app``).
The same server hosts the JSON API under /api and serves the vanilla
HTML/CSS/JS frontend bundled as package data in ``web/static/``.
"""
