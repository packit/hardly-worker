# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from enum import Enum


class TaskName(str, Enum):
    source_git_pr_to_dist_git_pr = "task.run_source_git_pr_to_dist_git_pr_handler"
    gitlab_ci_to_source_git_pr = "task.run_gitlab_ci_to_source_git_pr_handler"
    pagure_ci_to_source_git_pr = "task.run_pagure_ci_to_source_git_pr_handler"
