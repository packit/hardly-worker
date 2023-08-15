# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import re
from logging import getLogger
from os import getenv
from typing import Optional

from hardly.handlers.abstract import TaskName, reacts_to
from packit.config.job_config import JobConfig
from packit.config.package_config import PackageConfig
from packit_service.models import (
    PullRequestModel,
    ProjectEventModel,
    SourceGitPRDistGitPRModel,
)
from packit_service.worker.events import PipelineGitlabEvent
from packit_service.worker.events.pagure import PullRequestFlagPagureEvent
from packit_service.worker.handlers.abstract import JobHandler
from packit_service.worker.mixin import (
    ConfigFromEventMixin,
    PackitAPIWithUpstreamMixin,
)
from packit_service.worker.reporting import StatusReporter, BaseCommitStatus
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


class DistGitCIToSourceGitPRHandler(
    JobHandler,
    ConfigFromEventMixin,
    PackitAPIWithUpstreamMixin,
):
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

        self.status_state: Optional[BaseCommitStatus] = None
        self.status_description: Optional[str] = None
        self.status_check_name: Optional[str] = None
        self.status_url: Optional[str] = None

    def dist_git_pr_model(self) -> Optional[PullRequestModel]:
        raise NotImplementedError("This should have been implemented.")

    @staticmethod
    def get_gitlab_account_name() -> str:
        # https://github.com/packit/ogr/issues/751
        return {
            "stream-prod": "centos-stream-packit",
            "stream-stg": "packit-as-a-service-stg",
            "fedora-source-git-prod": "packit-as-a-service",
            "fedora-source-git-stg": "packit-as-a-service-stg",
        }[getenv("PROJECT", "stream-stg")]

    def run(self) -> TaskResults:
        """
        When a dist-git PR flag/pipeline is updated, create a commit
        status in the original source-git MR with the flag/pipeline info.
        """
        if not (dist_git_pr_model := self.dist_git_pr_model()):
            logger.debug("No dist-git PR model.")
            return TaskResults(success=True)
        if not (
            sg_dg := SourceGitPRDistGitPRModel.get_by_dist_git_id(dist_git_pr_model.id)
        ):
            logger.debug(f"Source-git PR for {dist_git_pr_model} not found.")
            return TaskResults(success=True)

        source_git_pr_model = sg_dg.source_git_pull_request
        source_git_project = self.service_config.get_project(
            url=source_git_pr_model.project.project_url
        )
        source_git_pr = source_git_project.get_pr(source_git_pr_model.pr_id)

        status_reporter = StatusReporter.get_instance(
            project=source_git_project,
            # The head_commit is the latest commit of the MR.
            # If there was a new commit pushed before the pipeline ended, the report
            # might be incorrect until the new (for the new commit) pipeline finishes.
            commit_sha=source_git_pr.head_commit,
            packit_user=self.get_gitlab_account_name(),
        )
        # Our account(s) have no access (unless it's manually added) into the fork repos,
        # to set the commit status (which would look like a Pipeline result)
        # so the status reporter fallbacks to adding a commit comment.
        # To not pollute MRs with too many comments, we might later skip
        # the 'Pipeline is pending/running' events.
        # See also https://github.com/packit/packit-service/issues/1411
        status_reporter.set_status(
            state=self.status_state,
            description=self.status_description,
            check_name=self.status_check_name,
            url=self.status_url,
        )
        return TaskResults(success=True)


@reacts_to(event=PipelineGitlabEvent)
class GitlabCIToSourceGitPRHandler(DistGitCIToSourceGitPRHandler):
    task_name = TaskName.gitlab_ci_to_source_git_pr

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

        # https://docs.gitlab.com/ee/api/pipelines.html#list-project-pipelines -> status
        self.status_state: BaseCommitStatus = {
            "pending": BaseCommitStatus.pending,
            "created": BaseCommitStatus.pending,
            "waiting_for_resource": BaseCommitStatus.pending,
            "preparing": BaseCommitStatus.pending,
            "scheduled": BaseCommitStatus.pending,
            "manual": BaseCommitStatus.pending,
            "running": BaseCommitStatus.running,
            "success": BaseCommitStatus.success,
            "skipped": BaseCommitStatus.success,
            "failed": BaseCommitStatus.failure,
            "canceled": BaseCommitStatus.failure,
        }[event["status"]]
        self.status_description: str = f"Changed status to {event['detailed_status']}"
        self.status_check_name: str = "Dist-git MR CI Pipeline"
        self.status_url: str = (
            f"{event['project_url']}/-/pipelines/{event['pipeline_id']}"
        )
        self.source: str = event["source"]
        self.merge_request_url: str = event["merge_request_url"]
        self.commit_sha = event["commit_sha"]

    def dist_git_pr_model(self) -> Optional[PullRequestModel]:
        if self.source == "merge_request_event":
            if not self.merge_request_url:
                logger.debug(f"No merge_request_url in {self.data.event_dict}")
                return None
            # Derive project from merge_request_url because
            # self.project can be either source or target
            if m := re.fullmatch(
                r"(\S+)/-/merge_requests/(\d+)", self.merge_request_url
            ):
                project = self.service_config.get_project(url=m[1])
                pr_model = PullRequestModel.get_or_create(
                    pr_id=int(m[2]),
                    namespace=project.namespace,
                    repo_name=project.repo,
                    project_url=m[1],
                )
                ProjectEventModel.get_or_create(
                    type=pr_model.project_event_model_type,
                    event_id=pr_model.id,
                    commit_sha=self.commit_sha,
                )
                return pr_model
        return None


@reacts_to(event=PullRequestFlagPagureEvent)
class PagureCIToSourceGitPRHandler(DistGitCIToSourceGitPRHandler):
    task_name = TaskName.pagure_ci_to_source_git_pr

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

        # https://pagure.io/api/0/#pull_requests-tab -> "Flag a pull-request" -> status
        self.status_state = {
            "pending": BaseCommitStatus.pending,
            "success": BaseCommitStatus.success,
            "error": BaseCommitStatus.error,
            "failure": BaseCommitStatus.failure,
            "canceled": BaseCommitStatus.failure,
        }[event["status"]]
        self.status_description = event["comment"]
        self.status_check_name = event["username"]
        self.status_url = event["url"]

    def dist_git_pr_model(self) -> Optional[PullRequestModel]:
        return self.data.db_project_object
