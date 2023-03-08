# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import json

import pytest

from tests.spellbook import DATA_DIR


@pytest.fixture(scope="module")
def mr_event():
    return json.loads((DATA_DIR / "webhooks" / "gitlab" / "mr_event.json").read_text())


@pytest.fixture(scope="module")
def pipeline_event():
    return json.loads((DATA_DIR / "webhooks" / "gitlab" / "pipeline.json").read_text())


@pytest.fixture(scope="module")
def fedora_dg_pr_flag_updated_event():
    return json.loads(
        (DATA_DIR / "fedmsg" / "fedora-dg-pr-flag-updated.json").read_text()
    )


@pytest.fixture(scope="module")
def gitlab_push_event():
    return json.loads((DATA_DIR / "webhooks" / "gitlab" / "push.json").read_text())


@pytest.fixture(scope="module")
def fedora_dg_push_event():
    return json.loads((DATA_DIR / "fedmsg" / "fedora-dg-push.json").read_text())
