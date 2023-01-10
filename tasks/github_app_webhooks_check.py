import logging
from datetime import datetime, timedelta
from typing import Iterable, List, Tuple

from shared.config import get_config
from shared.torngit import Github
from shared.torngit.exceptions import (
    TorngitRateLimitError,
    TorngitServer5xxCodeError,
    TorngitUnauthorizedError,
)

from app import celery_app
from helpers.environment import is_enterprise
from services.github import get_github_integration_token
from tasks.crontasks import CodecovCronTask

log = logging.getLogger(__name__)


class GitHubAppWebhooksCheckTask(CodecovCronTask):
    @classmethod
    def get_min_seconds_interval_between_executions(cls):
        return 86100  # 1 day - 5 minutes

    name = "app.cron.daily.GitHubAppWebhooksCheckTask"

    def _apply_time_filter(self, deliveries: List[object]) -> Iterable[object]:
        """
        Apply a time filter to the deliveries, so that we only consider webhook deliveries from the past 25h.
        So that we skip deliveries that we probably already analysed in the past.
        """
        now = datetime.now()
        yesterday_plus_hour = now - timedelta(hours=25)

        def time_filter(item: object) -> bool:
            return (
                datetime.strptime(item["delivered_at"], "%Y-%m-%dT%H:%M:%SZ")
                >= yesterday_plus_hour
            )

        return filter(time_filter, deliveries)

    def _apply_status_filter(self, deliveries: List[object]) -> Iterable[object]:
        """
        Apply a filter to the status code of the delivery so that we ignore successful deliveries.
        """

        def status_filter(item: object) -> bool:
            return item["status_code"] != 200

        return filter(status_filter, deliveries)

    def _apply_event_filter(self, deliveries: List[object]) -> Iterable[object]:
        """
        Apply a status filter. We really only care about installation webhooks for now.
        events: installation, installation_repositories
        """

        def event_filter(item: object) -> bool:
            return item["event"].startswith("installation")

        return filter(event_filter, deliveries)

    def apply_filters_to_deliveries(self, deliveries: List[object]) -> List[object]:
        filters_to_apply = [
            self._apply_time_filter,
            self._apply_status_filter,
            self._apply_event_filter,
        ]
        for current_filter in filters_to_apply:
            deliveries = current_filter(deliveries)
        return list(deliveries)

    def request_redeliveries(self, deliveries_to_request: List[object]):
        # TODO: complete me
        pass

    async def run_cron_task(self, db_session, *args, **kwargs):
        if is_enterprise():
            return dict(checked=False, reason="Enterprise env")

        gh_app_token = get_github_integration_token(
            service="github", integration_id=None
        )
        gh_handler = Github(
            token=dict(key=gh_app_token),
            oauth_consumer_token=dict(
                key=get_config("github", "client_id"),
                secret=get_config("github", "client_secret"),
            ),
        )
        redeliveries_requested = 0
        all_deliveries = 0
        pages_processed = 0
        try:
            async for deliveries in gh_handler.list_webhook_deliveries():
                all_deliveries += len(deliveries)
                pages_processed += 1
                deliveries_to_request = self.apply_filters_to_deliveries(deliveries)
                # TODO: Request redelivery of those deliveries
                self.request_redeliveries(deliveries_to_request)
                redeliveries_requested += len(deliveries_to_request)
        except (
            TorngitUnauthorizedError,
            TorngitServer5xxCodeError,
            TorngitRateLimitError,
        ) as exp:
            log.error(
                "Failed to check github app webhooks",
                extra=dict(
                    reason="Failed with exception. Ending task immediately",
                    exception=str(exp),
                    redeliveries_requested=redeliveries_requested,
                    deliveries_processed=all_deliveries,
                    pages_processed=pages_processed,
                ),
            )
            return dict(
                checked=False,
                reason="Failed with exception. Ending task immediately",
                exception=str(exp),
                redeliveries_requested=redeliveries_requested,
                deliveries_processed=all_deliveries,
                pages_processed=pages_processed,
            )
        return dict(
            checked=True,
            redeliveries_requested=redeliveries_requested,
            deliveries_processed=all_deliveries,
            pages_processed=pages_processed,
        )


RegisteredGitHubAppWebhooksCheckTask = celery_app.register_task(
    GitHubAppWebhooksCheckTask()
)
hourly_check_task = celery_app.tasks[RegisteredGitHubAppWebhooksCheckTask.name]