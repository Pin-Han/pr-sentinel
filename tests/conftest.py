import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_webhook_payload() -> dict:
    return json.loads((FIXTURES / "sample_webhook_payload.json").read_text())


@pytest.fixture
def sample_diff_small() -> str:
    return (FIXTURES / "sample_diff_small.patch").read_text()
