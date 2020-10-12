from datadog_checks.base import AgentCheck
from datadog_checks.mongo.collectors.base import MongoCollector


class SessionStatsCollector(MongoCollector):
    """TODO"""

    def collect(self, client):
        config_db = client["config"]
        try:
            # 3.6+ only
            sessions_count = next(
                config_db['system.sessions'].aggregate([{"$listSessions": {"allUsers": True}}, {"$count": "total"}])
            )['total']
        except Exception:
            self.log.info('Unable to fetch system.session statistics.')
            return
        metric_name = self._normalize("sessions.count", AgentCheck.gauge)
        self.check.gauge(metric_name, sessions_count, tags=self.base_tags)
