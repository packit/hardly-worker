# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import re
from logging import getLogger
from os import getenv
from typing import Optional

from hardly.constants import DISTGIT_TO_SOURCEGIT_PR_TITLE
from hardly.handlers.abstract import TaskName, reacts_to
from ogr.abstract import PullRequest
from packit.api import PackitAPI
from packit.config.job_config import JobConfig
from packit.config.package_config import PackageConfig
from packit.local_project import CALCULATE, LocalProject, LocalProjectBuilder
from packit_service.models import PullRequestModel, SourceGitPRDistGitPRModel
from packit_service.worker.events import MergeRequestGitlabEvent
from packit_service.worker.events.enums import GitlabEventAction
from packit_service.worker.handlers.abstract import JobHandler
from packit_service.worker.mixin import (
    ConfigFromEventMixin,
    PackitAPIWithUpstreamMixin,
)
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


def fix_bz_refs(message: str) -> str:
    """Convert Bugzilla references to the format accepted by BZ checks

    From
        Bugzilla: <bzid or bzlin>
    to
        Resolves: bz#<bzid>

    Args:
        message: Multiline string in which Bugzilla references are converted.

    Returns:
        Multiline string with BZ refs in the required format.
    """
    pattern = r"^Bugzilla: +(https://.+id=)?(\d+)"
    repl = r"Resolves: bz#\2"
    return re.sub(pattern, repl, message, flags=re.MULTILINE)


@reacts_to(event=MergeRequestGitlabEvent)
class SourceGitPRToDistGitPRHandler(
    JobHandler,
    ConfigFromEventMixin,
    PackitAPIWithUpstreamMixin,
):
    task_name = TaskName.source_git_pr_to_dist_git_pr

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
        self.action = event["action"]
        self.pr_identifier = event["identifier"]
        self.pr_title = event["title"]
        self.pr_description = event["description"]
        self.pr_url = event["url"]
        self.source_project_url = event["source_project_url"]
        self.target_repo = (
            f"{event['target_repo_namespace']}/{event['target_repo_name']}"
        )
        self.target_repo_branch = event["target_repo_branch"]
        self.oldrev = event["oldrev"]

        # lazy
        self._source_git_pr_model = None
        self._dist_git_pr_model = None
        self._dist_git_pr = None
        self._local_project: Optional[LocalProject] = None

    @property
    def source_git_pr_model(self) -> PullRequestModel:
        if not self._source_git_pr_model:
            self._source_git_pr_model = PullRequestModel.get_or_create(
                pr_id=self.pr_identifier,
                namespace=self.project.namespace,
                repo_name=self.project.repo,
                project_url=self.project.get_web_url(),
            )
        return self._source_git_pr_model

    @property
    def dist_git_pr_model(self) -> Optional[PullRequestModel]:
        if not self._dist_git_pr_model:
            if sg_dg := SourceGitPRDistGitPRModel.get_by_source_git_id(
                self.source_git_pr_model.id
            ):
                self._dist_git_pr_model = sg_dg.dist_git_pull_request
        return self._dist_git_pr_model

    @property
    def dist_git_pr(self) -> Optional[PullRequest]:
        if not self._dist_git_pr and self.dist_git_pr_model:
            dist_git_project = self.service_config.get_project(
                url=self.dist_git_pr_model.project.project_url
            )
            self._dist_git_pr = dist_git_project.get_pr(self.dist_git_pr_model.pr_id)
        return self._dist_git_pr

    @property
    def local_project(self) -> LocalProject:
        if not self._local_project:
            source_project = self.service_config.get_project(
                url=self.source_project_url
            )
            self._local_project = LocalProjectBuilder().build(
                git_project=source_project,
                ref=self.data.commit_sha,
                working_dir=self.service_config.command_handler_work_dir,
                git_repo=CALCULATE,
            )
            # We need to fetch tags from the upstream source-git repo
            # Details: https://github.com/packit/hardly/issues/61
            self._local_project.fetch(self.project.get_web_url(), force=True)
        return self._local_project

    @property
    def packit_api(self):
        if not self._packit_api:
            self._packit_api = PackitAPI(
                config=self.service_config,
                package_config=self.package_config,
                upstream_local_project=self.local_project,
            )
        return self._packit_api

    def sync_release(self) -> PullRequest:
        dg_pr_info = f"""###### Info for package maintainer
This MR has been automatically created from
[this source-git MR]({self.pr_url})."""
        if getenv("PROJECT", "").startswith("stream"):
            dg_pr_info += """
Please review the contribution and once you are comfortable with the content,
you should trigger a CI pipeline run via `Pipelines → Run pipeline`."""

        return self.packit_api.sync_release(
            dist_git_branch=self.target_repo_branch,
            version=self.packit_api.up.get_specfile_version(),
            add_new_sources=False,
            title=self.pr_title,
            description=f"{fix_bz_refs(self.pr_description)}\n\n---\n{dg_pr_info}",
            sync_default_files=False,
            # we rely on this in PipelineHandler below
            local_pr_branch_suffix=f"src-{self.pr_identifier}",
            mark_commit_origin=True,
        )

    def handle_existing_dist_git_pr(self) -> bool:
        """Sync changes in source-git PR to already existing dist-git PR.

        Returns:
            was the sync successful
        """
        logger.info(
            f"{self.source_git_pr_model} already has corresponding {self.dist_git_pr_model}"
        )
        if self.dist_git_pr:
            msg = ""
            if self.action == GitlabEventAction.closed.value:
                msg = f"[Source-git MR]({self.pr_url}) has been closed."
                self.dist_git_pr.close()
            elif self.action == GitlabEventAction.reopen.value:
                msg = f"[Source-git MR]({self.pr_url}) has been reopened."
                # https://github.com/packit/ogr/pull/714
                # self.dist_git_pr.reopen()
            elif self.action == GitlabEventAction.update.value:
                msg = f"[Source-git MR]({self.pr_url}) has been updated."
                # update the dist-git PR if there are code changes
                if self.oldrev:
                    self.sync_release()
            elif self.action == GitlabEventAction.opened.value:
                # Are you trying to re-send a webhook payload to the endpoint manually?
                # If so and you expect a new dist-git PR being opened, you first
                # have to remove the old relation from db.
                logger.error(f"[Source-git MR]({self.pr_url}) opened. (again???)")
                return False
            logger.info(msg)
            self.dist_git_pr.comment(msg)
        return True

    @staticmethod
    def dist_git_pr_in_db(dg_pr: PullRequest) -> bool:
        dg_pr_model = PullRequestModel.get_or_create(
            pr_id=dg_pr.id,
            namespace=dg_pr.target_project.namespace,
            repo_name=dg_pr.target_project.repo,
            project_url=dg_pr.target_project.get_web_url(),
        )
        if sg_dg := SourceGitPRDistGitPRModel.get_by_dist_git_id(dg_pr_model.id):
            logger.error(
                f"Packit didn't create a new dist-git MR probably because a MR (#{dg_pr.id}) "
                "with the same title & description & target branch already exists. "
                f"It was created from src-git MR #{sg_dg.source_git_pull_request.pr_id}."
            )
            return True
        return False

    def run(self) -> TaskResults:
        """
        If user creates a merge-request on the source-git repository,
        create a matching merge-request to the dist-git repository.
        """
        if self.pr_title.startswith(DISTGIT_TO_SOURCEGIT_PR_TITLE):
            logger.debug(f"{DISTGIT_TO_SOURCEGIT_PR_TITLE} PR opened by us.")
            return TaskResults(success=True)

        if not self.handle_target():
            logger.debug(
                "Not creating/updating a dist-git MR from "
                f"{self.target_repo}:{self.target_repo_branch}"
            )
            return TaskResults(success=True)

        if self.dist_git_pr_model:
            # There already is a corresponding dist-git MR, let's update it.
            return TaskResults(success=self.handle_existing_dist_git_pr())

        if not self.package_config:
            logger.debug("No package config found.")
            return TaskResults(success=True)

        if (
            self.target_repo_branch
            not in self.packit_api.dg.local_project.git_project.get_branches()
        ):
            msg = (
                "Can't create a dist-git pull/merge request out of this contribution "
                f"because matching {self.target_repo_branch} branch does not exist "
                f"in dist-git {self.target_repo} repo."
            )
            self.project.get_pr(int(self.pr_identifier)).comment(msg)
            logger.info(msg)
            return TaskResults(success=True)

        logger.info(f"About to create a dist-git MR from source-git MR {self.pr_url}")

        dg_pr = self.sync_release()
        # This check is probably not needed, it's here in case the #70 appears again.
        if self.dist_git_pr_in_db(dg_pr):
            return TaskResults(success=False)

        comment = f"""[Dist-git MR #{dg_pr.id}]({dg_pr.url})
has been created for sake of triggering the downstream checks.
It ensures that your contribution is valid and can be incorporated in
dist-git as it is still the authoritative source for the distribution.
We want to run checks there only so they don't need to be reimplemented in source-git as well."""
        self.project.get_pr(int(self.pr_identifier)).comment(comment)

        SourceGitPRDistGitPRModel.get_or_create(
            self.pr_identifier,
            self.project.namespace,
            self.project.repo,
            self.project.get_web_url(),
            dg_pr.id,
            dg_pr.target_project.namespace,
            dg_pr.target_project.repo,
            dg_pr.target_project.get_web_url(),
        )

        return TaskResults(success=True)

    def handle_target(self) -> bool:
        """Tell if a target repo and branch pair of an MR should be handled or ignored."""
        handled_targets = self.service_config.gitlab_mr_targets_handled

        # If nothing is configured, all targets are handled.
        if not handled_targets:
            return True

        for target in handled_targets:
            if re.fullmatch(target.repo or ".+", self.target_repo) and re.fullmatch(
                target.branch or ".+", self.target_repo_branch
            ):
                return True
        return False
