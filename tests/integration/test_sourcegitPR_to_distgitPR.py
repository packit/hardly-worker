# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import pytest
from flexmock import flexmock

from hardly.tasks import run_source_git_pr_to_dist_git_pr_handler
from ogr.services.gitlab import GitlabProject, GitlabPullRequest
from ogr.services.pagure import PagureProject
from packit.api import PackitAPI
from packit.config.job_config import JobConfigTriggerType
from packit.local_project import LocalProject
from packit.upstream import Upstream
from packit_service.config import ServiceConfig
from packit_service.constants import SANDCASTLE_WORK_DIR
from packit_service.models import PullRequestModel, SourceGitPRDistGitPRModel
from packit_service.service.db_triggers import AddPullRequestDbTrigger
from packit_service.utils import dump_package_config
from packit_service.worker.monitoring import Pushgateway
from packit_service.worker.parser import Parser
from tests.spellbook import first_dict_value

source_git_yaml = """ {
    "upstream_project_url": "https://github.com/vmware/open-vm-tools.git",
    "upstream_ref": "stable-11.3.0",
    "downstream_package_name": "open-vm-tools",
    "specfile_path": ".distro/open-vm-tools.spec",
    "patch_generation_ignore_paths": [".distro"],
    "patch_generation_patch_id_digits": 1,
    "sync_changelog": True,
    "synced_files": [
        {
            "src": ".distro/",
            "dest": ".",
            "delete": True,
            "filters": [
                "protect .git*",
                "protect sources",
                "exclude source-git.yaml",
                "exclude .gitignore",
            ],
        }
    ],
    "sources": [
        {
            "path": "open-vm-tools-11.3.0-18090558.tar.gz",
            "url": "https://sources.stream.centos.org/sources/rpms/open-vm-tools/...",
        }
    ],
}
"""


@pytest.mark.parametrize(
    "dist_git_branches, target_repo_branch",
    [
        pytest.param(
            ["master", "c9s"],
            "c9s",
            id="Use upstream branch name in downstream",
        ),
        pytest.param(
            ["master"],
            "c9s",
            id="Notify user that branch does not exist",
        ),
    ],
)
def test_source_git_pr_to_dist_git_pr(mr_event, dist_git_branches, target_repo_branch):
    version = "11.3.0"

    trigger = flexmock(
        job_config_trigger_type=JobConfigTriggerType.pull_request, id=123, pr_id=5
    )
    flexmock(AddPullRequestDbTrigger).should_receive("db_trigger").and_return(trigger)

    flexmock(GitlabProject).should_receive("get_file_content").and_return(
        source_git_yaml
    )

    flexmock(PullRequestModel).should_receive("get_or_create").and_return(
        flexmock(id=1)
    )
    flexmock(SourceGitPRDistGitPRModel).should_receive(
        "get_by_source_git_id"
    ).and_return(None)

    lp = flexmock(
        LocalProject,
        refresh_the_arguments=lambda: None,
        checkout_ref=lambda ref: None,
    )
    lp.should_receive("fetch").with_args(
        "https://gitlab.com/packit-service/src/open-vm-tools", force=True
    )
    flexmock(PagureProject).should_receive("get_branches").and_return(dist_git_branches)
    flexmock(Upstream).should_receive("get_specfile_version").and_return(version)

    config = ServiceConfig()
    config.command_handler_work_dir = SANDCASTLE_WORK_DIR
    config.gitlab_mr_targets_handled = None
    config.package_config_path_override = ".distro/source-git.yaml"
    flexmock(ServiceConfig).should_receive("get_service_config").and_return(config)
    flexmock(Pushgateway).should_receive("push").once().and_return()
    flexmock(GitlabPullRequest).should_receive("comment").and_return()
    if target_repo_branch in dist_git_branches:
        flexmock(SourceGitPRDistGitPRModel).should_receive("get_by_dist_git_id")
        flexmock(SourceGitPRDistGitPRModel).should_receive("get_or_create")
        (
            flexmock(PackitAPI)
            .should_receive("sync_release")
            .with_args(
                dist_git_branch=target_repo_branch,
                version=version,
                add_new_sources=False,
                title="Yet another testing MR",
                description="""DnD RpcV3: A corrupted packet received may result in an OOB
memory access if the length of the message received is less than the size
of the expected packet header.

---
###### Info for package maintainer
This MR has been automatically created from
[this source-git MR](https://gitlab.com/packit-service/src/open-vm-tools/-/merge_requests/5).""",
                sync_default_files=False,
                local_pr_branch_suffix="src-5",
                mark_commit_origin=True,
            )
            .once()
            .and_return(
                flexmock(
                    id=1,
                    target_project=flexmock(
                        namespace="", repo="", get_web_url=lambda: ""
                    ),
                    url="",
                )
            )
        )

    event = Parser.parse_event(mr_event)
    results = run_source_git_pr_to_dist_git_pr_handler(
        packages_config=dump_package_config(event.packages_config),
        event=event.get_dict(),
        job_config=None,
    )

    assert first_dict_value(results["job"])["success"]
