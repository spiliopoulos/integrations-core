from datadog_checks.mongo.collectors.base import MongoCollector


class ConnPoolStatsCollector(MongoCollector):
    """TODO"""

    def collect(self, client):
        db = client["admin"]
        stats = {'connection_pool': db.command('connPoolStats')}
        self._submit_payload(stats)
