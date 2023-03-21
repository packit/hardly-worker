# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from collections import defaultdict
from enum import Enum
from typing import Set, Type, Dict

from packit_service.worker.events import Event
from packit_service.worker.handlers import JobHandler

SUPPORTED_EVENTS_FOR_HANDLER: Dict[Type[JobHandler], Set[Type[Event]]] = defaultdict(
    set
)


def reacts_to(event: Type[Event]):
    def _add_to_mapping(kls: Type[JobHandler]):
        SUPPORTED_EVENTS_FOR_HANDLER[kls].add(event)
        return kls

    return _add_to_mapping


class TaskName(str, Enum):
    source_git_pr_to_dist_git_pr = "task.run_source_git_pr_to_dist_git_pr_handler"
    gitlab_ci_to_source_git_pr = "task.run_gitlab_ci_to_source_git_pr_handler"
    pagure_ci_to_source_git_pr = "task.run_pagure_ci_to_source_git_pr_handler"
    dist_git_to_source_git_pr = "task.run_dist_git_to_source_git_pr_handler"
