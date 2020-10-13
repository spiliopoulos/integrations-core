# (C) Datadog, Inc. 2020-present
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
from datadog_checks.dev.jmx import JVM_E2E_METRICS

METRICS = [
    'sonarqube.async_execution.largest_worker_count',
    'sonarqube.async_execution.queue_size',
    'sonarqube.async_execution.worker_count',
    'sonarqube.database.pool_active_connections',
    'sonarqube.database.pool_idle_connections',
    'sonarqube.database.pool_initial_size',
    'sonarqube.database.pool_min_idle_connections',
    'sonarqube.database.pool_max_active_connections',
    'sonarqube.database.pool_max_idle_connections',
    'sonarqube.database.pool_max_wait_millis',
    'sonarqube.database.pool_remove_abandoned_timeout_seconds',
] + JVM_E2E_METRICS
