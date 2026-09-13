from __future__ import annotations

from typing import Any

import pytest

from tests import helpers


@pytest.fixture
def sample_answers() -> dict[str, Any]:
    return helpers.sample_answers_dict()


@pytest.fixture
def sample_diagnosis_request() -> dict[str, Any]:
    return helpers.sample_diagnosis_request_dict()


@pytest.fixture
def sample_diagnosis_report_dict() -> dict[str, Any]:
    return helpers.sample_diagnosis_report_dict()


@pytest.fixture
def sample_prescription_request() -> dict[str, Any]:
    return helpers.sample_prescription_request_dict()


@pytest.fixture
def sample_prescription_report_dict() -> dict[str, Any]:
    return helpers.sample_prescription_report_dict()
