from fastapi.routing import APIRoute

from app.api.deps import get_db
from app.main import app


def _walk(dependant):
    for d in dependant.dependencies:
        yield d
        yield from _walk(d)


def _routes(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):  # FastAPI >= 0.13x lazily included routers
            yield from _routes(r.original_router.routes)


def test_every_get_db_dependency_commits_before_the_response():
    """FastAPI >= 0.121 runs request-scoped yield-dependency teardown (our
    commit) after the response is sent, so a client acting on a 200 could
    read uncommitted state (seen as 'SAFETY has not been validated yet')."""
    offenders = [
        r.path for r in _routes(app.routes)
        for d in _walk(r.dependant) if d.call is get_db and getattr(d, "scope", None) != "function"
    ]
    assert sum(1 for _ in _routes(app.routes)) > 20  # the walk really found the API
    assert offenders == []
