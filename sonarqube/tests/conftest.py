# (C) Datadog, Inc. 2020-present
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
import os

import pytest

from datadog_checks.dev import docker_run

from .common import CHECK_CONFIG, HERE


@pytest.fixture(scope='session')
def dd_environment():
    with docker_run(
        os.path.join(HERE, 'docker', 'docker-compose.yaml'), log_patterns=['SonarQube is up'], mount_logs=True
    ):
        yield CHECK_CONFIG, {'use_jmx': True}
