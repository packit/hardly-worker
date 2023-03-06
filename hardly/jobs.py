# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger
from typing import List

from hardly.handlers import (
    SourceGitPRToDistGitPRHandler,
    GitlabCIToSourceGitPRHandler,
    PagureCIToSourceGitPRHandler,
)
from packit_service.worker.events import (
    Event,
    MergeRequestGitlabEvent,
    PipelineGitlabEvent,
)
from packit_service.worker.events.pagure import PullRequestFlagPagureEvent
from packit_service.worker.jobs import SteveJobs
from packit_service.worker.parser import Parser
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


class StreamJobs(SteveJobs):
    def process_jobs(self, event: Event) -> List[TaskResults]:
        return []  # For now, don't process default jobs, i.e. copr-build & tests
        # return super().process_jobs(event)

    def process_message(self, event: dict) -> List[TaskResults]:
        """
        Entrypoint for message processing.

        :param event:  dict with webhook/fed-mes payload
        """

        event_object = Parser.parse_event(event)
        if not (event_object and event_object.pre_check()):
            return []

        # Handlers are (for now) run even the job is not configured in a package.
        if isinstance(event_object, MergeRequestGitlabEvent):
            SourceGitPRToDistGitPRHandler.get_signature(
                event=event_object,
                job=None,
            ).apply_async()

        if isinstance(event_object, PipelineGitlabEvent):
            GitlabCIToSourceGitPRHandler.get_signature(
                event=event_object,
                job=None,
            ).apply_async()

        if isinstance(event_object, PullRequestFlagPagureEvent):
            PagureCIToSourceGitPRHandler.get_signature(
                event=event_object,
                job=None,
            ).apply_async()

        return self.process_jobs(event_object)
