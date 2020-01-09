import logging
import re

from app import celery_app
from celery_config import status_set_pending_task_name
from covreports.helpers.yaml import walk, default_if_true
from covreports.utils.match import match
from covreports.utils.urls import make_url
from services.redis import get_redis_connection
from services.repository import get_repo_provider_service_by_id
from services.yaml.fetcher import fetch_current_yaml_from_provider_via_reference
from services.yaml.reader import read_yaml_field
from tasks.base import BaseCodecovTask

log = logging.getLogger(__name__)


class StatusSetPendingTask(BaseCodecovTask):
    """
    Set commit status to pending
    """
    name = status_set_pending_task_name

    async def run_async(self, db_session, repoid, commitid, branch, on_a_pull_request, *args, **kwargs):
        log.info(
            'Set pending',
            extra=dict(repoid=repoid, commitid=commitid, branch=branch, on_a_pull_request=on_a_pull_request)
        )

        # TODO: need to check for enterprise license once licences are implemented
        # assert license.LICENSE['valid'], ('Notifications disabled. '+(license.LICENSE['warning'] or ''))

        # check that repo is in beta
        redis_connection = get_redis_connection()
        assert redis_connection.sismember('beta.pending', repoid), 'Pending disabled. Please request to be in beta.'

        repo = get_repo_provider_service_by_id(db_session, repoid)

        current_yaml = await fetch_current_yaml_from_provider_via_reference(commitid, repo)
        settings = read_yaml_field(current_yaml, ('coverage', 'status'))

        if settings and any(settings.values()):
            statuses = await repo.get_commit_statuses(commitid)
            url = make_url(repo, 'commit', commitid)

            for context in ('project', 'patch', 'changes'):
                if settings.get(context):
                    for key, config in default_if_true(settings[context]):
                        try:
                            title = 'codecov/%s%s' % (context, ('/'+key if key != 'default' else ''))
                            assert match(config.get('branches'), branch or ''), 'Ignore setting pending status on branch'
                            assert on_a_pull_request if config.get('only_pulls', False) else True, 'Set pending only on pulls'
                            assert config.get('set_pending', True), 'Pending status disabled in YAML'
                            assert title not in statuses, 'Pending status already set'

                            await repo.set_commit_status(commit=commitid,
                                                         status='pending',
                                                         context=title,
                                                         description='Collecting reports and waiting for CI to complete',
                                                         url=url)
                            log.info(
                                'Status set',
                                extra=dict(context=title, state='pending')
                            )
                        except AssertionError as e:
                            log.warning(
                                str(e),
                                extra=dict(context=context)
                            )

RegisteredStatusSetPendingTask = celery_app.register_task(StatusSetPendingTask())
status_set_pending_task = celery_app.tasks[StatusSetPendingTask.name]
