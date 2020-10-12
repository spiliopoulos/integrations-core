from datadog_checks.base import AgentCheck
from datadog_checks.mongo.collectors import MongoCollector


class JumboStatsCollector(MongoCollector):
    def collect(self, client):
        chunks = client['config']['chunks']
        total_chunks_count = chunks.count_documents({})
        jumbo_chunks_count = chunks.count_documents({'jumbo': True})

        total_chunks_metric_name = self._normalize("chunks.total", AgentCheck.gauge)
        jumbo_chunks_metric_name = self._normalize("chunks.jumbo", AgentCheck.gauge)
        self.check.gauge(total_chunks_metric_name, total_chunks_count, tags=self.base_tags)
        self.check.gauge(jumbo_chunks_metric_name, jumbo_chunks_count, tags=self.base_tags)
