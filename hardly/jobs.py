# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger
from typing import List, Set, Type, Optional

from hardly.handlers.abstract import SUPPORTED_EVENTS_FOR_HANDLER
from packit_service.worker.events import Event
from packit_service.worker.handlers import JobHandler
from packit_service.worker.parser import Parser
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


class StreamJobs:
    """
    Similar to packit_service.SteveJobs, but we don't inherit from it
    because there's actually a very few we have in common.
    """

    def __init__(self, event: Optional[Event] = None):
        self.event = event

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

        self.event = Parser.parse_event(event)
        if not (self.event and self.event.pre_check()):
            return []

        for handler_class in self.get_handlers_for_event():
            handler_class.get_signature(
                event=self.event,
                job=None,
            ).apply_async()

        return []
