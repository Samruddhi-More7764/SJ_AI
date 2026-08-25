"""
Pytest configuration and shared fixtures for Vanna v2 test suite.
"""

import os
import pytest
import sqlite3
from pathlib import Path

# Configure pytest-asyncio
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "anthropic: marks tests requiring Anthropic API key"
    )
    config.addinivalue_line("markers", "openai: marks tests requiring OpenAI API key")
    config.addinivalue_line(
        "markers", "azureopenai: marks tests requiring Azure OpenAI API key"
    )
    config.addinivalue_line("markers", "gemini: marks tests requiring Google API key")
    config.addinivalue_line("markers", "ollama: marks tests requiring Ollama")
    config.addinivalue_line("markers", "chromadb: marks tests requiring ChromaDB")
    config.addinivalue_line("markers", "legacy: marks tests for LegacyVannaAdapter")


def pytest_collection_modifyitems(config, items):
    """Automatically skip tests if required API keys are missing."""
    for item in items:
        # Skip Anthropic tests if no API key
        if "anthropic" in item.keywords:
            if not os.getenv("ANTHROPIC_API_KEY"):
                item.add_marker(
                    pytest.mark.skip(
                        reason="ANTHROPIC_API_KEY environment variable not set"
                    )
                )

        # Skip OpenAI tests if no API key
        if "openai" in item.keywords:
            if not os.getenv("OPENAI_API_KEY"):
                item.add_marker(
                    pytest.mark.skip(
                        reason="OPENAI_API_KEY environment variable not set"
                    )
                )

        # Skip Azure OpenAI tests if no API key
        if "azureopenai" in item.keywords:
            if not os.getenv("AZURE_OPENAI_API_KEY"):
                item.add_marker(
                    pytest.mark.skip(
                        reason="AZURE_OPENAI_API_KEY environment variable not set"
                    )
                )

        # Skip Gemini tests if no API key
        if "gemini" in item.keywords:
            if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
                item.add_marker(
                    pytest.mark.skip(
                        reason="GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set"
                    )
                )


@pytest.fixture(scope="session")
def chinook_db():
    pytest.skip("SqliteRunner was removed; StockJarvis uses Postgres only.")
