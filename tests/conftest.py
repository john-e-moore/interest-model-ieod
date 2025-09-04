from pathlib import Path
import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def input_dir(project_root: Path) -> Path:
    return project_root / "input"


@pytest.fixture(scope="session")
def fixtures_dir(project_root: Path) -> Path:
    return project_root / "tests" / "fixtures"


@pytest.fixture()
def tmp_output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out

import os
from pathlib import Path
import pytest

@pytest.fixture(scope=session)
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]

@pytest.fixture(scope=session)
def input_dir(project_root: Path) -> Path:
    return project_root / input

@pytest.fixture(scope=session)
def fixtures_dir(project_root: Path) -> Path:
    return project_root / tests / fixtures

@pytest.fixture()
def tmp_output_dir(tmp_path: Path) -> Path:
    out = tmp_path / output
    out.mkdir(parents=True, exist_ok=True)
    return out
