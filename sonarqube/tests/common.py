# (C) Datadog, Inc. 2020-present
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
from datadog_checks.dev import get_docker_hostname, get_here, load_jmx_config

HERE = get_here()
HOST = get_docker_hostname()
PORT = 10443

INSTANCES = [{'host': HOST, 'port': PORT}]

CHECK_CONFIG = load_jmx_config()
CHECK_CONFIG['instances'] = INSTANCES
