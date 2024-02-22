# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import pytest

from hardly.handlers import (
    DistGitToSourceGitPRHandler,
    GitlabCIToSourceGitPRHandler,
    PagureCIToSourceGitPRHandler,
    SourceGitPRToDistGitPRHandler,
)
from hardly.jobs import StreamJobs
from packit_service.worker.events import (
    MergeRequestGitlabEvent,
    PipelineGitlabEvent,
    PushGitlabEvent,
    PushPagureEvent,
)
from packit_service.worker.events.pagure import PullRequestFlagPagureEvent


@pytest.mark.parametrize(
    "event_cls,expected_handlers",
    [
        pytest.param(
            MergeRequestGitlabEvent,
            {SourceGitPRToDistGitPRHandler},
            id="MergeRequestGitlabEvent->SourceGitPRToDistGitPRHandler",
        ),
        pytest.param(
            PipelineGitlabEvent,
            {GitlabCIToSourceGitPRHandler},
            id="PipelineGitlabEvent->GitlabCIToSourceGitPRHandler",
        ),
        pytest.param(
            PullRequestFlagPagureEvent,
            {PagureCIToSourceGitPRHandler},
            id="PullRequestFlagPagureEvent->PagureCIToSourceGitPRHandler",
        ),
        pytest.param(
            PushGitlabEvent,
            {DistGitToSourceGitPRHandler},
            id="PushGitlabEvent->DistGitToSourceGitPRHandler",
        ),
        pytest.param(
            PushPagureEvent,
            {DistGitToSourceGitPRHandler},
            id="PushPagureEvent->DistGitToSourceGitPRHandler",
        ),
    ],
)
def test_get_handlers_for_event(event_cls, expected_handlers):
    # We are using isinstance for matching event to handlers
    # and flexmock can't do this for us, so we need a subclass to test it.
    # (And real event classes have a lot of __init__ arguments.)
    class Event(event_cls):
        def __init__(self):
            pass

    event = Event()
    assert StreamJobs(event).get_handlers_for_event() == expected_handlers
