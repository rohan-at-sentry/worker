from textwrap import dedent
from unittest.mock import PropertyMock

import pytest
from shared.bundle_analysis.comparison import BundleChange, RouteChange
from shared.bundle_analysis.models import AssetType
from shared.bundle_analysis.storage import get_bucket_name
from shared.config import PATCH_CENTRIC_DEFAULT_CONFIG
from shared.yaml import UserYaml

from database.enums import ReportType
from database.models import CommitReport, MeasurementName
from database.tests.factories import CommitFactory, PullFactory, UploadFactory
from database.tests.factories.timeseries import DatasetFactory, Measurement
from services.archive import ArchiveService
from services.bundle_analysis.notify import (
    BundleAnalysisNotifyReturn,
    BundleAnalysisNotifyService,
)
from services.bundle_analysis.notify.types import NotificationType
from services.bundle_analysis.report import (
    BundleAnalysisReportService,
    ProcessingResult,
)
from services.repository import EnrichedPull
from services.urls import get_bundle_analysis_pull_url


class MockBundleReport:
    def __init__(self, name):
        self.name = name

    def total_size(self):
        return 123456

    def is_cached(self):
        return self.name.startswith("cached")


def hook_mock_repo_provider(mocker, mock_repo_provider):
    USING_GET_REPO_PROVIDER = [
        "services.bundle_analysis.notify.contexts.get_repo_provider_service",
    ]
    for usage in USING_GET_REPO_PROVIDER:
        mocker.patch(
            usage,
            return_value=mock_repo_provider,
        )


def hook_mock_pull(mocker, mock_pull):
    USING_MOCK_PULL = [
        "services.bundle_analysis.notify.contexts.comment.fetch_and_update_pull_request_information_from_commit",
        "services.bundle_analysis.notify.contexts.commit_status.fetch_and_update_pull_request_information_from_commit",
    ]
    for usage in USING_MOCK_PULL:
        mocker.patch(usage, return_value=mock_pull)


@pytest.mark.parametrize(
    "bundle_changes, bundle_routes_changes, percent_change, user_config, expected_message",
    [
        pytest.param(
            [
                BundleChange(
                    bundle_name="added-bundle",
                    change_type=BundleChange.ChangeType.ADDED,
                    size_delta=12345,
                    percentage_delta=5.56,
                ),
                BundleChange(
                    bundle_name="changed-bundle",
                    change_type=BundleChange.ChangeType.CHANGED,
                    size_delta=3456,
                    percentage_delta=0.35,
                ),
                BundleChange(
                    bundle_name="removed-bundle",
                    change_type=BundleChange.ChangeType.REMOVED,
                    size_delta=-1234,
                    percentage_delta=-1.23,
                ),
            ],
            {},
            5.56,
            {
                **PATCH_CENTRIC_DEFAULT_CONFIG,
                "bundle_analysis": {
                    "status": "informational",
                    "warning_threshold": ["percentage", 5.0],
                },
            },
            dedent("""\
            ## [Bundle](URL) Report

            Changes will increase total bundle size by 14.57kB (5.56%) :arrow_up::warning:, exceeding the [configured](https://docs.codecov.com/docs/javascript-bundle-analysis#main-features) threshold of 5%.

            | Bundle name | Size | Change |
            | ----------- | ---- | ------ |
            | added-bundle | 123.46kB | 12.35kB (5.56%) :arrow_up::warning: |
            | changed-bundle | 123.46kB | 3.46kB (0.35%) :arrow_up: |
            | removed-bundle | (removed) | 1.23kB (-1.23%) :arrow_down: |
            """),
            id="comment_increase_size_warning",
        ),
        pytest.param(
            [
                BundleChange(
                    bundle_name="added-bundle",
                    change_type=BundleChange.ChangeType.ADDED,
                    size_delta=12345,
                    percentage_delta=5.56,
                ),
                BundleChange(
                    bundle_name="changed-bundle",
                    change_type=BundleChange.ChangeType.CHANGED,
                    size_delta=3456,
                    percentage_delta=2.56,
                ),
                BundleChange(
                    bundle_name="removed-bundle",
                    change_type=BundleChange.ChangeType.REMOVED,
                    size_delta=-1234,
                    percentage_delta=-100.0,
                ),
            ],
            {},
            5.56,
            {
                **PATCH_CENTRIC_DEFAULT_CONFIG,
                "bundle_analysis": {
                    "status": True,
                    "warning_threshold": ["absolute", 10000],
                },
            },
            dedent("""\
            ## [Bundle](URL) Report

            :x: Check failed: changes will increase total bundle size by 14.57kB (5.56%) :arrow_up:, **exceeding** the [configured](https://docs.codecov.com/docs/javascript-bundle-analysis#main-features) threshold of 10.0kB.

            | Bundle name | Size | Change |
            | ----------- | ---- | ------ |
            | added-bundle | 123.46kB | 12.35kB (5.56%) :arrow_up::x: |
            | changed-bundle | 123.46kB | 3.46kB (2.56%) :arrow_up: |
            | removed-bundle | (removed) | 1.23kB (-100.0%) :arrow_down: |
            """),
            id="comment_increase_size_error",
        ),
        pytest.param(
            [
                BundleChange(
                    bundle_name="added-bundle",
                    change_type=BundleChange.ChangeType.ADDED,
                    size_delta=12345,
                    percentage_delta=2.56,
                ),
                BundleChange(
                    bundle_name="cached-bundle",
                    change_type=BundleChange.ChangeType.CHANGED,
                    size_delta=3456,
                    percentage_delta=2.56,
                ),
                BundleChange(
                    bundle_name="removed-bundle",
                    change_type=BundleChange.ChangeType.REMOVED,
                    size_delta=-1234,
                    percentage_delta=2.56,
                ),
            ],
            {},
            3.46,
            {
                **PATCH_CENTRIC_DEFAULT_CONFIG,
                "bundle_analysis": {
                    "status": "informational",
                    "warning_threshold": ["percentage", 5.0],
                },
            },
            dedent("""\
            ## [Bundle](URL) Report

            Changes will increase total bundle size by 14.57kB (3.46%) :arrow_up:. This is within the [configured](https://docs.codecov.com/docs/javascript-bundle-analysis#main-features) threshold :white_check_mark:

            <details><summary>Detailed changes</summary>

            | Bundle name | Size | Change |
            | ----------- | ---- | ------ |
            | added-bundle | 123.46kB | 12.35kB (2.56%) :arrow_up: |
            | cached-bundle* | 123.46kB | 3.46kB (2.56%) :arrow_up: |
            | removed-bundle | (removed) | 1.23kB (2.56%) :arrow_down: |

            </details>

            ℹ️ *Bundle size includes cached data from a previous commit

            """),
            id="comment_increase_size_cached_values",
        ),
        pytest.param(
            [
                BundleChange(
                    bundle_name="test-bundle",
                    change_type=BundleChange.ChangeType.CHANGED,
                    size_delta=-3456,
                    percentage_delta=-2.56,
                ),
            ],
            {},
            -0.52,
            {
                **PATCH_CENTRIC_DEFAULT_CONFIG,
                "bundle_analysis": {
                    "status": "informational",
                    "warning_threshold": ["percentage", 5.0],
                },
            },
            dedent("""\
            ## [Bundle](URL) Report

            Changes will decrease total bundle size by 3.46kB (-0.52%) :arrow_down:. This is within the [configured](https://docs.codecov.com/docs/javascript-bundle-analysis#main-features) threshold :white_check_mark:

            <details><summary>Detailed changes</summary>

            | Bundle name | Size | Change |
            | ----------- | ---- | ------ |
            | test-bundle | 123.46kB | 3.46kB (-2.56%) :arrow_down: |

            </details>
            """),
            id="comment_decrease_size",
        ),
        pytest.param(
            [
                BundleChange(
                    bundle_name="test-bundle",
                    change_type=BundleChange.ChangeType.CHANGED,
                    size_delta=0,
                    percentage_delta=0.0,
                ),
            ],
            {},
            0,
            {
                **PATCH_CENTRIC_DEFAULT_CONFIG,
                "bundle_analysis": {
                    "status": "informational",
                    "warning_threshold": ["percentage", 5.0],
                },
            },
            dedent("""\
            ## [Bundle](URL) Report

            Bundle size has no change :white_check_mark:


        """),
            id="comment_no_change",
        ),
        pytest.param(
            [
                BundleChange(
                    bundle_name="added-bundle",
                    change_type=BundleChange.ChangeType.ADDED,
                    size_delta=12345,
                    percentage_delta=5.56,
                ),
                BundleChange(
                    bundle_name="changed-bundle",
                    change_type=BundleChange.ChangeType.CHANGED,
                    size_delta=3456,
                    percentage_delta=0.35,
                ),
                BundleChange(
                    bundle_name="removed-bundle",
                    change_type=BundleChange.ChangeType.REMOVED,
                    size_delta=-1234,
                    percentage_delta=-1.23,
                ),
            ],
            {
                "BundleA": [
                    RouteChange(
                        route_name="/users",
                        change_type=RouteChange.ChangeType.ADDED,
                        size_delta=1000,
                        size_base=0,
                        size_head=1000,
                        percentage_delta=100,
                    ),
                    RouteChange(
                        route_name="/faq",
                        change_type=RouteChange.ChangeType.REMOVED,
                        size_delta=-5000,
                        size_base=5000,
                        size_head=0,
                        percentage_delta=-100.0,
                    ),
                    RouteChange(
                        route_name="/careers",
                        change_type=RouteChange.ChangeType.CHANGED,
                        size_delta=10000,
                        size_base=20000,
                        size_head=30000,
                        percentage_delta=50.0,
                    ),
                    RouteChange(
                        route_name="/no-change",
                        change_type=RouteChange.ChangeType.CHANGED,
                        size_delta=0,
                        size_base=999999,
                        size_head=999999,
                        percentage_delta=0,
                    ),
                ],
                "BundleB": [
                    RouteChange(
                        route_name="/users",
                        change_type=RouteChange.ChangeType.ADDED,
                        size_delta=1000,
                        size_base=0,
                        size_head=1000,
                        percentage_delta=100,
                    ),
                    RouteChange(
                        route_name="/faq",
                        change_type=RouteChange.ChangeType.REMOVED,
                        size_delta=-5000,
                        size_base=5000,
                        size_head=0,
                        percentage_delta=-100.0,
                    ),
                    RouteChange(
                        route_name="/about-us",
                        change_type=RouteChange.ChangeType.CHANGED,
                        size_delta=10000,
                        size_base=20000,
                        size_head=30000,
                        percentage_delta=50.0,
                    ),
                ],
            },
            5.56,
            {
                **PATCH_CENTRIC_DEFAULT_CONFIG,
                "bundle_analysis": {
                    "status": "informational",
                    "warning_threshold": ["percentage", 5.0],
                },
            },
            dedent("""\
            ## [Bundle](URL) Report

            Changes will increase total bundle size by 14.57kB (5.56%) :arrow_up::warning:, exceeding the [configured](https://docs.codecov.com/docs/javascript-bundle-analysis#main-features) threshold of 5%.

            | Bundle name | Size | Change |
            | ----------- | ---- | ------ |
            | added-bundle | 123.46kB | 12.35kB (5.56%) :arrow_up::warning: |
            | changed-bundle | 123.46kB | 3.46kB (0.35%) :arrow_up: |
            | removed-bundle | (removed) | 1.23kB (-1.23%) :arrow_down: |

            <details>
              <summary>View changes by path for bundle: BundleA</summary>

            | File path | Size | Change |
            | --------- | ---- | ------ |
            | **/users** _(New)_ | 1.0kB | 1.0kB (100%) :rocket: |
            | ~~**/faq**~~ _(Deleted)_ | 0 bytes | 5.0kB (-100.0%) :wastebasket: |
            | /careers | 30.0kB | 10.0kB (50.0%)  |

            </details>

            <details>
              <summary>View changes by path for bundle: BundleB</summary>

            | File path | Size | Change |
            | --------- | ---- | ------ |
            | **/users** _(New)_ | 1.0kB | 1.0kB (100%) :rocket: |
            | ~~**/faq**~~ _(Deleted)_ | 0 bytes | 5.0kB (-100.0%) :wastebasket: |
            | /about-us | 30.0kB | 10.0kB (50.0%)  |

            </details>

            """),
            id="comparison_by_file_path",
        ),
    ],
)
def test_bundle_analysis_notify(
    bundle_changes: list[BundleChange],
    bundle_routes_changes: dict[str, list[RouteChange]],
    percent_change: float,
    user_config: dict,
    expected_message: str,
    dbsession,
    mocker,
    mock_storage,
    mock_repo_provider,
):
    hook_mock_repo_provider(mocker, mock_repo_provider)
    base_commit = CommitFactory()
    dbsession.add(base_commit)
    base_commit_report = CommitReport(
        commit=base_commit, report_type=ReportType.BUNDLE_ANALYSIS.value
    )
    dbsession.add(base_commit_report)

    head_commit = CommitFactory(repository=base_commit.repository)
    dbsession.add(head_commit)
    head_commit_report = CommitReport(
        commit=head_commit, report_type=ReportType.BUNDLE_ANALYSIS.value
    )
    dbsession.add(head_commit_report)

    pull = PullFactory(
        repository=base_commit.repository,
        head=head_commit.commitid,
        base=base_commit.commitid,
        compared_to=base_commit.commitid,
    )
    dbsession.add(pull)
    dbsession.commit()

    notifier = BundleAnalysisNotifyService(head_commit, UserYaml.from_dict(user_config))

    repo_key = ArchiveService.get_archive_hash(base_commit.repository)
    mock_storage.write_file(
        get_bucket_name(),
        f"v1/repos/{repo_key}/{base_commit_report.external_id}/bundle_report.sqlite",
        "test-content",
    )
    mock_storage.write_file(
        get_bucket_name(),
        f"v1/repos/{repo_key}/{head_commit_report.external_id}/bundle_report.sqlite",
        "test-content",
    )

    mocker.patch("shared.bundle_analysis.report.BundleAnalysisReport._setup")

    mocker.patch(
        "shared.bundle_analysis.comparison.BundleAnalysisComparison.bundle_changes",
        return_value=bundle_changes,
    )
    mocker.patch(
        "shared.bundle_analysis.comparison.BundleAnalysisComparison.bundle_routes_changes",
        return_value=bundle_routes_changes,
    )
    mock_percentage = mocker.patch(
        "shared.bundle_analysis.comparison.BundleAnalysisComparison.percentage_delta",
        new_callable=PropertyMock,
    )
    mock_percentage.return_value = percent_change

    mocker.patch(
        "shared.bundle_analysis.report.BundleAnalysisReport.bundle_report",
        side_effect=lambda name: MockBundleReport(name),
    )

    hook_mock_pull(
        mocker,
        EnrichedPull(
            database_pull=pull,
            provider_pull={},
        ),
    )

    mock_check_compare_sha = mocker.patch(
        "shared.bundle_analysis.comparison.BundleAnalysisComparison._check_compare_sha"
    )
    mock_check_compare_sha.return_value = None

    expected_message = expected_message.replace(
        "URL", get_bundle_analysis_pull_url(pull=pull)
    )

    mock_repo_provider.post_comment.return_value = {"id": "test-comment-id"}

    success = notifier.notify()
    assert success == BundleAnalysisNotifyReturn(
        notifications_configured=(
            NotificationType.PR_COMMENT,
            NotificationType.COMMIT_STATUS,
        ),
        notifications_attempted=(
            NotificationType.PR_COMMENT,
            NotificationType.COMMIT_STATUS,
        ),
        notifications_successful=(
            NotificationType.PR_COMMENT,
            NotificationType.COMMIT_STATUS,
        ),
    )

    assert pull.bundle_analysis_commentid is not None
    mock_repo_provider.post_comment.assert_called_once_with(
        pull.pullid, expected_message
    )

    success = notifier.notify()
    assert success == BundleAnalysisNotifyReturn(
        notifications_configured=(
            NotificationType.PR_COMMENT,
            NotificationType.COMMIT_STATUS,
        ),
        notifications_attempted=(
            NotificationType.PR_COMMENT,
            NotificationType.COMMIT_STATUS,
        ),
        notifications_successful=(
            NotificationType.PR_COMMENT,
            NotificationType.COMMIT_STATUS,
        ),
    )

    assert pull.bundle_analysis_commentid is not None
    mock_repo_provider.edit_comment.assert_called_once_with(
        pull.pullid, "test-comment-id", expected_message
    )


@pytest.mark.asyncio
async def test_bundle_analysis_save_measurements_report_size(
    dbsession, mocker, mock_storage
):
    storage_path = (
        "v1/repos/testing/ed1bdd67-8fd2-4cdb-ac9e-39b99e4a3892/bundle_report.sqlite"
    )
    mock_storage.write_file(get_bucket_name(), storage_path, "test-content")

    commit = CommitFactory()
    dbsession.add(commit)
    dbsession.commit()

    commit_report = CommitReport(
        commit=commit, report_type=ReportType.BUNDLE_ANALYSIS.value
    )
    dbsession.add(commit_report)
    dbsession.commit()

    upload = UploadFactory.create(storage_path=storage_path, report=commit_report)
    dbsession.add(upload)
    dbsession.commit()

    dataset = DatasetFactory.create(
        name=MeasurementName.bundle_analysis_report_size.value,
        repository_id=commit.repository.repoid,
    )
    dbsession.add(dataset)
    dbsession.commit()

    class MockBundleReport:
        def __init__(self, bundle_name, size):
            self.bundle_name = bundle_name
            self.size = size

        @property
        def name(self):
            return self.bundle_name

        def total_size(self):
            return self.size

    class MockBundleAnalysisReport:
        def bundle_report(self, bundle_name):
            return MockBundleReport("BundleA", 1111)

    mocker.patch(
        "shared.bundle_analysis.BundleAnalysisReportLoader.load",
        return_value=MockBundleAnalysisReport(),
    )

    report_service = BundleAnalysisReportService(UserYaml.from_dict({}))
    result: ProcessingResult = report_service.save_measurements(
        commit, upload, "BundleA"
    )

    assert result.error is None

    measurements = (
        dbsession.query(Measurement)
        .filter_by(
            name=MeasurementName.bundle_analysis_report_size.value,
            commit_sha=commit.commitid,
            timestamp=commit.timestamp,
            measurable_id="BundleA",
        )
        .all()
    )

    assert len(measurements) == 1
    assert measurements[0].value == 1111

    measurements = (
        dbsession.query(Measurement)
        .filter_by(
            name=MeasurementName.bundle_analysis_report_size.value,
            commit_sha=commit.commitid,
            timestamp=commit.timestamp,
            measurable_id="BundleB",
        )
        .all()
    )

    assert len(measurements) == 0


@pytest.mark.asyncio
async def test_bundle_analysis_save_measurements_asset_size(
    dbsession, mocker, mock_storage
):
    storage_path = (
        "v1/repos/testing/ed1bdd67-8fd2-4cdb-ac9e-39b99e4a3892/bundle_report.sqlite"
    )
    mock_storage.write_file(get_bucket_name(), storage_path, "test-content")

    commit = CommitFactory()
    dbsession.add(commit)
    dbsession.commit()

    commit_report = CommitReport(
        commit=commit, report_type=ReportType.BUNDLE_ANALYSIS.value
    )
    dbsession.add(commit_report)
    dbsession.commit()

    upload = UploadFactory.create(storage_path=storage_path, report=commit_report)
    dbsession.add(upload)
    dbsession.commit()

    dataset = DatasetFactory.create(
        name=MeasurementName.bundle_analysis_asset_size.value,
        repository_id=commit.repository.repoid,
    )
    dbsession.add(dataset)
    dbsession.commit()

    class MockAssetReport:
        def __init__(self, mock_uuid, mock_size, mock_type):
            self.mock_uuid = mock_uuid
            self.mock_size = mock_size
            self.mock_type = mock_type

        @property
        def uuid(self):
            return self.mock_uuid

        @property
        def size(self):
            return self.mock_size

        @property
        def asset_type(self):
            return self.mock_type

    class MockBundleReport:
        def __init__(self, bundle_name, size):
            self.bundle_name = bundle_name
            self.size = size

        @property
        def name(self):
            return self.bundle_name

        def total_size(self):
            return self.size

        def asset_reports(self):
            return [
                MockAssetReport("UUID1", 123, AssetType.JAVASCRIPT),
                MockAssetReport("UUID2", 321, AssetType.JAVASCRIPT),
            ]

    class MockBundleAnalysisReport:
        def bundle_report(self, bundle_name):
            return MockBundleReport("BundleA", 1111)

    mocker.patch(
        "shared.bundle_analysis.BundleAnalysisReportLoader.load",
        return_value=MockBundleAnalysisReport(),
    )

    report_service = BundleAnalysisReportService(UserYaml.from_dict({}))
    result: ProcessingResult = report_service.save_measurements(
        commit, upload, "BundleA"
    )

    assert result.error is None

    measurements = (
        dbsession.query(Measurement)
        .filter_by(
            name=MeasurementName.bundle_analysis_asset_size.value,
            commit_sha=commit.commitid,
            timestamp=commit.timestamp,
            measurable_id="UUID1",
        )
        .all()
    )

    assert len(measurements) == 1
    assert measurements[0].value == 123

    measurements = (
        dbsession.query(Measurement)
        .filter_by(
            name=MeasurementName.bundle_analysis_asset_size.value,
            commit_sha=commit.commitid,
            timestamp=commit.timestamp,
            measurable_id="UUID2",
        )
        .all()
    )

    assert len(measurements) == 1
    assert measurements[0].value == 321


@pytest.mark.asyncio
async def test_bundle_analysis_save_measurements_asset_type_sizes(
    dbsession, mocker, mock_storage
):
    storage_path = (
        "v1/repos/testing/ed1bdd67-8fd2-4cdb-ac9e-39b99e4a3892/bundle_report.sqlite"
    )
    mock_storage.write_file(get_bucket_name(), storage_path, "test-content")

    commit = CommitFactory()
    dbsession.add(commit)
    dbsession.commit()

    commit_report = CommitReport(
        commit=commit, report_type=ReportType.BUNDLE_ANALYSIS.value
    )
    dbsession.add(commit_report)
    dbsession.commit()

    upload = UploadFactory.create(storage_path=storage_path, report=commit_report)
    dbsession.add(upload)
    dbsession.commit()

    measurements_datasets = [
        MeasurementName.bundle_analysis_stylesheet_size,
        MeasurementName.bundle_analysis_font_size,
        MeasurementName.bundle_analysis_image_size,
        MeasurementName.bundle_analysis_javascript_size,
    ]
    for measurement in measurements_datasets:
        dataset = DatasetFactory.create(
            name=measurement.value,
            repository_id=commit.repository.repoid,
        )
        dbsession.add(dataset)
        dbsession.commit()

    class MockAssetReport:
        def __init__(self, mock_uuid, mock_size, mock_type):
            self.mock_uuid = mock_uuid
            self.mock_size = mock_size
            self.mock_type = mock_type

        @property
        def uuid(self):
            return self.mock_uuid

        @property
        def size(self):
            return self.mock_size

        @property
        def asset_type(self):
            return self.mock_type

    class MockBundleReport:
        def __init__(self, bundle_name, size):
            self.bundle_name = bundle_name
            self.size = size

        @property
        def name(self):
            return self.bundle_name

        def total_size(self):
            return self.size

        def asset_reports(self):
            return [
                MockAssetReport("UUID1", 111, AssetType.JAVASCRIPT),
                MockAssetReport("UUID2", 222, AssetType.FONT),
                MockAssetReport("UUID3", 333, AssetType.IMAGE),
                MockAssetReport("UUID4", 444, AssetType.STYLESHEET),
            ]

    class MockBundleAnalysisReport:
        def bundle_report(self, bundle_name):
            return MockBundleReport("BundleA", 1111)

    mocker.patch(
        "shared.bundle_analysis.BundleAnalysisReportLoader.load",
        return_value=MockBundleAnalysisReport(),
    )

    report_service = BundleAnalysisReportService(UserYaml.from_dict({}))
    result: ProcessingResult = report_service.save_measurements(
        commit, upload, "BundleA"
    )

    assert result.error is None

    measurements = (
        dbsession.query(Measurement)
        .filter_by(
            name=MeasurementName.bundle_analysis_javascript_size.value,
            commit_sha=commit.commitid,
            timestamp=commit.timestamp,
            measurable_id="BundleA",
        )
        .all()
    )

    assert len(measurements) == 1
    assert measurements[0].value == 111

    measurements = (
        dbsession.query(Measurement)
        .filter_by(
            name=MeasurementName.bundle_analysis_font_size.value,
            commit_sha=commit.commitid,
            timestamp=commit.timestamp,
            measurable_id="BundleA",
        )
        .all()
    )

    assert len(measurements) == 1
    assert measurements[0].value == 222

    measurements = (
        dbsession.query(Measurement)
        .filter_by(
            name=MeasurementName.bundle_analysis_image_size.value,
            commit_sha=commit.commitid,
            timestamp=commit.timestamp,
            measurable_id="BundleA",
        )
        .all()
    )

    assert len(measurements) == 1
    assert measurements[0].value == 333

    measurements = (
        dbsession.query(Measurement)
        .filter_by(
            name=MeasurementName.bundle_analysis_stylesheet_size.value,
            commit_sha=commit.commitid,
            timestamp=commit.timestamp,
            measurable_id="BundleA",
        )
        .all()
    )

    assert len(measurements) == 1
    assert measurements[0].value == 444


@pytest.mark.asyncio
async def test_bundle_analysis_save_measurements_error(dbsession, mocker, mock_storage):
    storage_path = (
        "v1/repos/testing/ed1bdd67-8fd2-4cdb-ac9e-39b99e4a3892/bundle_report.sqlite"
    )
    mock_storage.write_file(get_bucket_name(), storage_path, "test-content")

    commit = CommitFactory()
    dbsession.add(commit)
    dbsession.commit()

    commit_report = CommitReport(
        commit=commit, report_type=ReportType.BUNDLE_ANALYSIS.value
    )
    dbsession.add(commit_report)
    dbsession.commit()

    upload = UploadFactory.create(storage_path=storage_path, report=commit_report)
    dbsession.add(upload)
    dbsession.commit()

    dataset = DatasetFactory.create(
        name=MeasurementName.bundle_analysis_asset_size.value,
        repository_id=commit.repository.repoid,
    )
    dbsession.add(dataset)
    dbsession.commit()

    mocker.patch(
        "shared.bundle_analysis.BundleAnalysisReportLoader.load",
        return_value=None,
    )

    report_service = BundleAnalysisReportService(UserYaml.from_dict({}))
    result: ProcessingResult = report_service.save_measurements(
        commit, upload, "BundleA"
    )

    assert result.error is not None
