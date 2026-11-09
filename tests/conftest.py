"""Shared fixtures and constants. Later tasks add fakes here."""

DIM = 8  # embedding dimension used by contract tests

import pytest_asyncio

from omnistream.store.memory import InMemoryStore


@pytest_asyncio.fixture(params=["memory"], ids=["memory"])
async def store(request):
    """GraphStore under test. Task 3 adds a "neo4j" param marked integration."""
    if request.param == "memory":
        yield InMemoryStore()
