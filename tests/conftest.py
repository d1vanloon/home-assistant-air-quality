from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "281078.csv"


@pytest.fixture
def sensor_csv() -> str:
    return FIXTURE_CSV.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    pass
