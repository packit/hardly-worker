# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import os

import pytest
from flexmock import flexmock

from hardly.jobs import StreamJobs
from ogr.abstract import GitProject
from packit.api import PackitAPI
from packit.local_project import LocalProject
from packit_service.config import ServiceConfig
from packit_service.constants import SANDCASTLE_WORK_DIR
from packit_service.worker.parser import Parser


@pytest.mark.parametrize(
    "event, dist_git_project_url, sourcegit_namespace, src_project_url",
    [
        pytest.param(
            "gitlab_push_event",
            "https://gitlab.com/packit-service/rpms/open-vm-tools",
            None,
            "https://gitlab.com/packit-service/src/open-vm-tools",
            id="Gitlab push",
        ),
        pytest.param(
            "fedora_dg_push_event",
            "https://src.fedoraproject.org/rpms/python-httpretty",
            "fedora/src",
            "https://gitlab.com/fedora/src/python-httpretty",
            id="Pagure push",
        ),
    ],
)
def test_distgit_to_sourcegit_pr(
    event,
    dist_git_project_url,
    sourcegit_namespace,
    src_project_url,
    request,
):
    event = Parser.parse_event(request.getfixturevalue(event))
    handler = StreamJobs(event).get_handlers_for_event().pop()

    config = ServiceConfig()
    config.command_handler_work_dir = SANDCASTLE_WORK_DIR
    config.package_config_path_override = ".distro/source-git.yaml"
    sc = flexmock(ServiceConfig)
    sc.should_receive("get_service_config").and_return(config)

    flexmock(
        LocalProject,
        refresh_the_arguments=lambda: None,
        checkout_ref=lambda ref: None,
        # FlexmockError: LocalProject does not have attribute 'namespace' ???
        # namespace="packit-service/rpms",
    )

    if sourcegit_namespace:
        os.environ["SOURCEGIT_NAMESPACE"] = sourcegit_namespace

    # TODO: make me work
    # flexmock(PackageConfigGetter).should_receive("get_package_config_from_repo").once()
    # sc.should_receive("get_project").with_args(url=dist_git_project_url).once()
    # sc.should_receive("get_project").with_args(url=src_project_url).once()

    flexmock(GitProject).should_receive("exists").and_return(True)

    flexmock(PackitAPI).should_receive("sync_push")

    handler(
        package_config=None,
        job_config=None,
        event=event.get_dict(),
    ).run()
