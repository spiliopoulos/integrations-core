# (C) Datadog, Inc. 2018-present
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
from __future__ import division

from copy import deepcopy
from distutils.version import LooseVersion

import pymongo
from six import PY3, itervalues

from datadog_checks.base import AgentCheck, ConfigurationError, is_affirmative
from datadog_checks.base.utils.common import exclude_undefined_keys
from datadog_checks.mongo.collectors import (
    CollStatsCollector,
    CustomQueriesCollector,
    DbStatCollector,
    FsyncLockCollector,
    IndexStatsCollector,
    ReplicaCollector,
    ReplicationOpLogCollector,
    ServerStatusCollector,
    TopCollector,
)
from datadog_checks.mongo.common import (
    DEFAULT_TIMEOUT,
    SERVICE_CHECK_NAME,
    MongosDeployment,
    ReplicaSetDeployment,
    StandaloneDeployment,
)

from . import metrics
from .utils import build_connection_string, parse_mongo_uri

if PY3:
    long = int


class MongoDb(AgentCheck):
    """
    MongoDB agent check.

    # Metrics
    Metric available for collection are listed by topic as `MongoDb` class variables.

    Various metric topics are collected by default. Others require the
    corresponding option enabled in the check configuration file.

    ## Format
    Metrics are listed with the following format:
        ```
        metric_name -> metric_type
        ```
        or
        ```
        metric_name -> (metric_type, alias)*
        ```

    * `alias` parameter is optional, if unspecified, MongoDB metrics are reported
       with their original metric names.

    # Service checks
    Available service checks:
    * `mongodb.can_connect`
      Connectivity health to the instance.
    * `mongodb.replica_set_member_state`
      Disposition of the member replica set state.
    """

    def __init__(self, name, init_config, instances=None):
        super(MongoDb, self).__init__(name, init_config, instances)

        # x.509 authentication
        self.ssl_params = exclude_undefined_keys(
            {
                'ssl': self.instance.get('ssl', None),
                'ssl_keyfile': self.instance.get('ssl_keyfile', None),
                'ssl_certfile': self.instance.get('ssl_certfile', None),
                'ssl_cert_reqs': self.instance.get('ssl_cert_reqs', None),
                'ssl_ca_certs': self.instance.get('ssl_ca_certs', None),
            }
        )

        if 'server' in self.instance:
            self.warning('Option `server` is deprecated and will be removed in a future release. Use `hosts` instead.')
            self.server = self.instance['server']
        else:
            hosts = self.instance.get('hosts', [])
            if not hosts:
                raise ConfigurationError('No `hosts` specified')

            username = self.instance.get('username')
            password = self.instance.get('password')

            if password and not username:
                raise ConfigurationError('`username` must be set when a `password` is specified')

            self.server = build_connection_string(
                hosts,
                scheme=self.instance.get('connection_scheme', 'mongodb'),
                username=username,
                password=password,
                database=self.instance.get('database'),
                options=self.instance.get('options'),
            )

        (
            self.username,
            self.password,
            self.db_name,
            self.nodelist,
            self.clean_server_name,
            self.auth_source,
        ) = parse_mongo_uri(self.server, sanitize_username=bool(self.ssl_params))

        self.additional_metrics = self.instance.get('additional_metrics', [])

        # Get the list of metrics to collect
        self.collect_tcmalloc_metrics = 'tcmalloc' in self.additional_metrics
        self.metrics_to_collect = self._build_metric_list_to_collect()

        if not self.db_name:
            self.log.info('No MongoDB database found in URI. Defaulting to admin.')
            self.db_name = 'admin'

        # Tagging
        custom_tags = list(set(self.instance.get('tags', [])))
        self.service_check_tags = ["db:%s" % self.db_name] + custom_tags

        # ...add the `server` tag to the metrics' tags only
        # (it's added in the backend for service checks)
        self.base_tags = custom_tags + ['server:%s' % self.clean_server_name]

        if self.nodelist:
            host = self.nodelist[0][0]
            port = self.nodelist[0][1]
            self.service_check_tags = self.service_check_tags + ["host:%s" % host, "port:%s" % port]

        self.timeout = float(self.instance.get('timeout', DEFAULT_TIMEOUT)) * 1000

        # Authenticate
        self.do_auth = True
        self.use_x509 = self.ssl_params and not self.password
        if not self.username:
            self.log.debug(u"A username is required to authenticate to `%s`", self.server)
            self.do_auth = False

        self.replica_check = is_affirmative(self.instance.get('replica_check', True))
        self.collections_indexes_stats = is_affirmative(self.instance.get('collections_indexes_stats'))
        self.coll_names = self.instance.get('collections', [])
        self.custom_queries = self.instance.get("custom_queries", [])
        # By default consider that this instance is a standalone, updated on each check run.
        self.deployment = StandaloneDeployment()
        self.collectors = []
        self.last_states_by_server = {}

    @classmethod
    def get_library_versions(cls):
        return {'pymongo': pymongo.version}

    def refresh_collectors(self, mongo_version, all_dbs, tags):
        collectors = []
        if isinstance(self.deployment, ReplicaSetDeployment):
            if self.replica_check:
                collectors.append(ReplicaCollector(self, tags))
            collectors.append(ReplicationOpLogCollector(self, tags))

        if not isinstance(self.deployment, MongosDeployment):
            # The local database contains different information on each node.
            # But is only available for mongod instances.
            collectors.append(DbStatCollector(self, "local", tags))
            collectors.append(FsyncLockCollector(self, self.db_name, tags))
            if 'top' in self.additional_metrics:
                collectors.append(TopCollector(self, tags))

        if self.deployment.is_principal():
            if 'local' in all_dbs:
                # Already monitored for all instances
                all_dbs.remove('local')
            for db_name in all_dbs:
                collectors.append(DbStatCollector(self, db_name, tags))

            if self.collections_indexes_stats:
                if LooseVersion(mongo_version) >= LooseVersion("3.2"):
                    collectors.append(IndexStatsCollector(self, self.db_name, tags, self.coll_names))
                else:
                    msg = "'collections_indexes_stats' is only available starting from mongo 3.2: "
                    "your mongo version is %s"
                    self.log.error(msg, mongo_version)
            collectors.append(CollStatsCollector(self, self.db_name, tags, coll_names=self.coll_names))

        # TODO: Is it the right place for custom queries?
        collectors.append(CustomQueriesCollector(self, self.db_name, tags, self.custom_queries))
        collectors.append(ServerStatusCollector(self, self.db_name, tags, tcmalloc=self.collect_tcmalloc_metrics))
        self.collectors = collectors

    def _build_metric_list_to_collect(self):
        """
        Build the metric list to collect based on the instance preferences.
        """
        metrics_to_collect = {}

        # Default metrics
        for default_metrics in itervalues(metrics.DEFAULT_METRICS):
            metrics_to_collect.update(default_metrics)

        # Additional metrics metrics
        for option in self.additional_metrics:
            additional_metrics = metrics.AVAILABLE_METRICS.get(option)
            if not additional_metrics:
                if option in metrics.DEFAULT_METRICS:
                    self.log.warning(
                        u"`%s` option is deprecated. The corresponding metrics are collected by default.", option
                    )
                else:
                    self.log.warning(
                        u"Failed to extend the list of metrics to collect: unrecognized `%s` option", option
                    )
                continue

            self.log.debug(u"Adding `%s` corresponding metrics to the list of metrics to collect.", option)
            metrics_to_collect.update(additional_metrics)

        return metrics_to_collect

    def _authenticate(self, database):
        """
        Authenticate to the database.

        Available mechanisms:
        * Username & password
        * X.509

        More information:
        https://api.mongodb.com/python/current/examples/authentication.html
        """
        authenticated = False
        try:
            # X.509
            if self.use_x509:
                self.log.debug(u"Authenticate `%s`  to `%s` using `MONGODB-X509` mechanism", self.username, database)
                authenticated = database.authenticate(self.username, mechanism='MONGODB-X509')

            # Username & password
            else:
                authenticated = database.authenticate(self.username, self.password)

        except pymongo.errors.PyMongoError as e:
            self.log.error(u"Authentication failed due to invalid credentials or configuration issues. %s", e)

        if not authenticated:
            message = "Mongo: cannot connect with config %s" % self.clean_server_name
            self.service_check(SERVICE_CHECK_NAME, AgentCheck.CRITICAL, tags=self.service_check_tags, message=message)
            raise Exception(message)

        return authenticated

    @staticmethod
    def get_deployment(admindb):
        # getCmdLineOpts is the runtime configuration of the mongo instance. Helpful to know whether the node is
        # a mongos or mongod, if the mongod is in a shard, if it's in a replica set, etc.
        options = admindb.command("getCmdLineOpts")['parsed']
        in_shard = False
        if 'sharding' in options:
            if 'configDB' in options['sharding']:
                return MongosDeployment()
            elif 'clusterRole' in options['sharding']:
                in_shard = True

        if 'replSetName' in options.get('replication', {}):
            repl_set_payload = admindb.command("replSetGetStatus")
            replset_name = repl_set_payload["set"]
            replset_state = repl_set_payload["myState"]
            return ReplicaSetDeployment(replset_name, replset_state, in_shard=in_shard)

        return StandaloneDeployment()

    def check(self, _):
        try:
            cli = pymongo.mongo_client.MongoClient(
                self.server,
                socketTimeoutMS=self.timeout,
                connectTimeoutMS=self.timeout,
                serverSelectionTimeoutMS=self.timeout,
                read_preference=pymongo.ReadPreference.PRIMARY_PREFERRED,
                **self.ssl_params
            )
            if self.do_auth:
                self.log.info("Using '%s' as the authentication database", self.auth_source)
                self._authenticate(cli[self.auth_source])
        except Exception:
            self.service_check(SERVICE_CHECK_NAME, AgentCheck.CRITICAL, tags=self.service_check_tags)
            raise

        try:
            mongo_version = cli.server_info().get('version', '0.0')
            self.set_metadata('version', mongo_version)
        except Exception:
            self.service_check(SERVICE_CHECK_NAME, AgentCheck.CRITICAL, tags=self.service_check_tags)
            self.log.exception("Error when collecting the version from the mongo server.")
            raise
        else:
            self.service_check(SERVICE_CHECK_NAME, AgentCheck.OK, tags=self.service_check_tags)

        tags = deepcopy(self.base_tags)

        self.deployment = self.get_deployment(cli['admin'])
        if isinstance(self.deployment, ReplicaSetDeployment):
            tags.extend(
                [
                    "replset_name:{}".format(self.deployment.replset_name),
                    "replset_state:{}".format(self.deployment.replset_state_name),
                ]
            )
        dbnames = cli.list_database_names()
        self.gauge('mongodb.dbs', len(dbnames), tags=tags)
        self.refresh_collectors(mongo_version, dbnames, tags)
        for collector in self.collectors:
            collector.collect(cli)
