# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger
from os import getenv
from typing import Optional

from hardly.constants import (
    DISTGIT_TO_SOURCEGIT_PR_TITLE,
    SOURCEGIT_URL,
    SOURCEGIT_NAMESPACE,
)
from hardly.handlers.abstract import TaskName, reacts_to
from packit.api import PackitAPI
from packit.config.job_config import JobConfig
from packit.config.package_config import PackageConfig
from packit.constants import DISTGIT_NAMESPACE
from packit.local_project import CALCULATE, LocalProject, LocalProjectBuilder
from packit_service.config import PackageConfigGetter
from packit_service.worker.events import PushGitlabEvent, PushPagureEvent
from packit_service.worker.handlers.abstract import JobHandler
from packit_service.worker.mixin import (
    ConfigFromEventMixin,
    PackitAPIWithUpstreamMixin,
)
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


@reacts_to(event=PushGitlabEvent)
@reacts_to(event=PushPagureEvent)
class DistGitToSourceGitPRHandler(
    JobHandler,
    ConfigFromEventMixin,
    PackitAPIWithUpstreamMixin,
):
    task_name = TaskName.dist_git_to_source_git_pr

    def __init__(
        self,
        package_config: PackageConfig,
        job_config: JobConfig,
        event: dict,
    ):
        super().__init__(
            package_config=package_config,
            job_config=job_config,
            event=event,
        )
        self._source_git_local_project: Optional[LocalProject] = None
        self._dist_git_local_project: Optional[LocalProject] = None
        self._lp_builder = LocalProjectBuilder()

    @property
    def source_git_local_project(self):
        if not self._source_git_local_project:
            dg_lp = self.dist_git_local_project
            base_url = getenv("SOURCEGIT_URL", SOURCEGIT_URL)
            # If the source-git namespace can't be derived from dist-git
            # namespace by just replacing rpms->src
            # (e.g. src @ gitlab, rpms @ pagure)
            # then it must be defined as env. var.
            if not (namespace := getenv("SOURCEGIT_NAMESPACE")):
                namespace = dg_lp.namespace.replace(
                    f"{DISTGIT_NAMESPACE}", f"{SOURCEGIT_NAMESPACE}"
                )
            # Assume the repo name is the same
            project_url = f"{base_url}{namespace}/{dg_lp.repo_name}.git"
            project = self.service_config.get_project(url=project_url)
            self._source_git_local_project = (
                self._lp_builder.build(
                    git_project=project, git_repo=CALCULATE, working_dir=CALCULATE
                )
                if project.exists()
                else None
            )
        return self._source_git_local_project

    @property
    def dist_git_local_project(self):
        if not self._dist_git_local_project:
            self._dist_git_local_project = self._lp_builder.build(
                git_project=self.project,
                ref=self.data.commit_sha,
                working_dir=self.service_config.command_handler_work_dir,
                git_repo=CALCULATE,
                namespace=CALCULATE,
                repo_name=CALCULATE,
            )
        return self._dist_git_local_project

    @property
    def packit_api(self):
        if not self._packit_api:
            # The package_config we got in __init__() is most likely None
            # because there's usually no .packit.yaml in dist-git repos.
            # We need to get the one from the source-git repo.
            self.package_config = PackageConfigGetter.get_package_config_from_repo(
                project=self.source_git_local_project.git_project
            )
            self._packit_api = PackitAPI(
                config=self.service_config,
                package_config=self.package_config,
                upstream_local_project=self.source_git_local_project,
                downstream_local_project=self.dist_git_local_project,
            )
        return self._packit_api

    def run(self):
        """
        As a reaction to dist-git being updated,
        update the source-git repo by opening a PR.
        """
        if not self.source_git_local_project:
            logger.debug(f"There's no source-git repo for {self.project}")
            return TaskResults(success=True)

        branch = self.data.git_ref
        if branch not in self.source_git_local_project.git_project.get_branches():
            logger.info(f"No {branch!r} branch in source-git repo to update")
            return TaskResults(success=True)

        # Expect for now that the branches are named the same in dist-git and source-git
        logger.debug(
            f"About to sync {self.dist_git_local_project.git_project}#{branch}"
            f" to {self.source_git_local_project.git_project}#{branch}"
        )
        self.packit_api.sync_push(
            dist_git_branch=branch,
            source_git_branch=branch,
            title=DISTGIT_TO_SOURCEGIT_PR_TITLE,
        )

        return TaskResults(success=True)
