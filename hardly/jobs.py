# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger
from typing import List, Set, Type

from hardly.handlers.abstract import SUPPORTED_EVENTS_FOR_HANDLER
from packit_service.worker.handlers import JobHandler
from packit_service.worker.jobs import SteveJobs
from packit_service.worker.parser import Parser
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


class StreamJobs(SteveJobs):
    def get_handlers_for_event(self) -> Set[Type[JobHandler]]:
        matching_handlers = {
            handler
            for handler in SUPPORTED_EVENTS_FOR_HANDLER.keys()
            if isinstance(self.event, tuple(SUPPORTED_EVENTS_FOR_HANDLER[handler]))
        }
        if not matching_handlers:
            logger.debug(f"No handler found for event:\n{self.event.__class__}")
        logger.debug(f"Matching handlers: {matching_handlers}")

        return matching_handlers

    def process_message(self, event: dict) -> List[TaskResults]:
        """
        Entrypoint for message processing.

        :param event:  dict with webhook/fed-mes payload
        """

        event_object = Parser.parse_event(event)
        if not (event_object and event_object.pre_check()):
            return []

        for handler_class in self.get_handlers_for_event():
            handler_class.get_signature(
                event=self.event,
                job=None,
            ).apply_async()

        return []
