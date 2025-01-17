import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional

import sentry_sdk
from sentry_sdk import metrics as sentry_metrics
from shared.bundle_analysis import (
    BundleAnalysisReport,
    BundleAnalysisReportLoader,
)
from shared.bundle_analysis.models import AssetType
from shared.bundle_analysis.storage import get_bucket_name
from shared.reports.enums import UploadState
from shared.storage.exceptions import FileNotInStorageError, PutRequestRateLimitError
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from database.enums import ReportType
from database.models.core import Commit
from database.models.reports import CommitReport, Upload, UploadError
from database.models.timeseries import Measurement, MeasurementName
from services.archive import ArchiveService
from services.report import BaseReportService
from services.storage import get_storage_client
from services.timeseries import repository_datasets_query


@dataclass
class ProcessingError:
    code: str
    params: Dict[str, Any]
    is_retryable: bool = False

    def as_dict(self):
        return {"code": self.code, "params": self.params}


@dataclass
class ProcessingResult:
    upload: Upload
    commit: Commit
    bundle_report: Optional[BundleAnalysisReport] = None
    session_id: Optional[int] = None
    error: Optional[ProcessingError] = None

    def as_dict(self):
        return {
            "upload_id": self.upload.id_,
            "session_id": self.session_id,
            "error": self.error.as_dict() if self.error else None,
        }

    def update_upload(self):
        """
        Updates this result's `Upload` record with information from
        this result.
        """
        db_session = self.upload.get_db_session()

        if self.error:
            self.commit.state = "error"
            self.upload.state = "error"
            self.upload.state_id = UploadState.ERROR.db_id

            upload_error = UploadError(
                upload_id=self.upload.id_,
                error_code=self.error.code,
                error_params=self.error.params,
            )
            db_session.add(upload_error)
        else:
            assert self.bundle_report is not None
            self.commit.state = "complete"
            self.upload.state = "processed"
            self.upload.state_id = UploadState.PROCESSED.db_id
            self.upload.order_number = self.session_id

        sentry_metrics.incr(
            "bundle_analysis_upload",
            tags={
                "result": "upload_error" if self.error else "processed",
            },
        )

        db_session.flush()


class BundleAnalysisReportService(BaseReportService):
    async def initialize_and_save_report(
        self, commit: Commit, report_code: str = None
    ) -> CommitReport:
        db_session = commit.get_db_session()

        commit_report = (
            db_session.query(CommitReport)
            .filter_by(
                commit_id=commit.id_,
                code=report_code,
                report_type=ReportType.BUNDLE_ANALYSIS.value,
            )
            .first()
        )
        if not commit_report:
            commit_report = CommitReport(
                commit_id=commit.id_,
                code=report_code,
                report_type=ReportType.BUNDLE_ANALYSIS.value,
            )
            db_session.add(commit_report)
            db_session.flush()
        return commit_report

    def _previous_bundle_analysis_report(
        self, bundle_loader: BundleAnalysisReportLoader, commit: Commit
    ) -> Optional[BundleAnalysisReport]:
        """
        Helper function to fetch the parent commit's BAR for the purpose of matching previous bundle's
        Assets to the current one being parsed.
        """
        if commit.parent_commit_id is None:
            return None

        db_session = commit.get_db_session()
        parent_commit = (
            db_session.query(Commit)
            .filter_by(
                commitid=commit.parent_commit_id,
                repository=commit.repository,
            )
            .first()
        )
        if parent_commit is None:
            return None

        parent_commit_report = (
            db_session.query(CommitReport)
            .filter_by(
                commit_id=parent_commit.id_,
                report_type=ReportType.BUNDLE_ANALYSIS.value,
            )
            .first()
        )
        if parent_commit_report is None:
            return None

        return bundle_loader.load(parent_commit_report.external_id)

    @sentry_sdk.trace
    def process_upload(self, commit: Commit, upload: Upload) -> ProcessingResult:
        """
        Download and parse the data associated with the given upload and
        merge the results into a bundle report.
        """
        commit_report: CommitReport = upload.report
        repo_hash = ArchiveService.get_archive_hash(commit_report.commit.repository)
        storage_service = get_storage_client()
        bundle_loader = BundleAnalysisReportLoader(storage_service, repo_hash)

        # fetch existing bundle report from storage
        bundle_report = bundle_loader.load(commit_report.external_id)

        if bundle_report is None:
            bundle_report = BundleAnalysisReport()

        # download raw upload data to local tempfile
        _, local_path = tempfile.mkstemp()
        try:
            with open(local_path, "wb") as f:
                storage_service.read_file(
                    get_bucket_name(), upload.storage_path, file_obj=f
                )

            # load the downloaded data into the bundle report
            session_id = bundle_report.ingest(local_path)

            # Retrieve previous commit's BAR and associate past Assets
            prev_bar = self._previous_bundle_analysis_report(bundle_loader, commit)
            if prev_bar:
                bundle_report.associate_previous_assets(prev_bar)

            # save the bundle report back to storage
            bundle_loader.save(bundle_report, commit_report.external_id)
        except FileNotInStorageError:
            return ProcessingResult(
                upload=upload,
                commit=commit,
                error=ProcessingError(
                    code="file_not_in_storage",
                    params={"location": upload.storage_path},
                    is_retryable=True,
                ),
            )
        except PutRequestRateLimitError as e:
            plugin_name = getattr(e, "bundle_analysis_plugin_name", "unknown")
            sentry_metrics.incr(
                "bundle_analysis_upload",
                tags={
                    "result": "rate_limit_error",
                    "plugin_name": plugin_name,
                },
            )
            return ProcessingResult(
                upload=upload,
                commit=commit,
                error=ProcessingError(
                    code="rate_limit_error",
                    params={"location": upload.storage_path},
                    is_retryable=True,
                ),
            )
        except Exception as e:
            # Metrics to count number of parsing errors of bundle files by plugins
            plugin_name = getattr(e, "bundle_analysis_plugin_name", "unknown")
            sentry_metrics.incr(
                "bundle_analysis_upload",
                tags={
                    "result": "parser_error",
                    "plugin_name": plugin_name,
                },
            )
            return ProcessingResult(
                upload=upload,
                commit=commit,
                error=ProcessingError(
                    code="parser_error",
                    params={
                        "location": upload.storage_path,
                        "plugin_name": plugin_name,
                    },
                    is_retryable=False,
                ),
            )
        finally:
            os.remove(local_path)

        return ProcessingResult(
            upload=upload,
            commit=commit,
            bundle_report=bundle_report,
            session_id=session_id,
        )

    def _save_to_timeseries(
        self,
        db_session: Session,
        commit: Commit,
        name: str,
        measurable_id: str,
        value: float,
    ):
        command = postgresql.insert(Measurement.__table__).values(
            name=name,
            owner_id=commit.repository.ownerid,
            repo_id=commit.repoid,
            measurable_id=measurable_id,
            branch=commit.branch,
            commit_sha=commit.commitid,
            timestamp=commit.timestamp,
            value=value,
        )
        command = command.on_conflict_do_update(
            index_elements=[
                Measurement.name,
                Measurement.owner_id,
                Measurement.repo_id,
                Measurement.measurable_id,
                Measurement.commit_sha,
                Measurement.timestamp,
            ],
            set_=dict(
                branch=command.excluded.branch,
                value=command.excluded.value,
            ),
        )
        db_session.execute(command)
        db_session.flush()

    @sentry_sdk.trace
    def save_measurements(self, commit: Commit, upload: Upload) -> ProcessingResult:
        """
        Save timeseries measurements for this bundle analysis report
        """
        try:
            commit_report: CommitReport = upload.report
            repo_hash = ArchiveService.get_archive_hash(commit_report.commit.repository)
            storage_service = get_storage_client()
            bundle_loader = BundleAnalysisReportLoader(storage_service, repo_hash)

            # fetch existing bundle report from storage
            bundle_analysis_report = bundle_loader.load(commit_report.external_id)

            dataset_names = [
                dataset.name for dataset in repository_datasets_query(commit.repository)
            ]

            db_session = commit.get_db_session()
            for bundle_report in bundle_analysis_report.bundle_reports():
                # For overall bundle size
                if MeasurementName.bundle_analysis_report_size.value in dataset_names:
                    self._save_to_timeseries(
                        db_session,
                        commit,
                        MeasurementName.bundle_analysis_report_size.value,
                        bundle_report.name,
                        bundle_report.total_size(),
                    )

                # For individual javascript associated assets using UUID
                if MeasurementName.bundle_analysis_asset_size.value in dataset_names:
                    for asset in bundle_report.asset_reports():
                        if asset.asset_type == AssetType.JAVASCRIPT:
                            self._save_to_timeseries(
                                db_session,
                                commit,
                                MeasurementName.bundle_analysis_asset_size.value,
                                asset.uuid,
                                asset.size,
                            )

                # For asset types sizes
                asset_type_map = {
                    MeasurementName.bundle_analysis_font_size: AssetType.FONT,
                    MeasurementName.bundle_analysis_image_size: AssetType.IMAGE,
                    MeasurementName.bundle_analysis_stylesheet_size: AssetType.STYLESHEET,
                    MeasurementName.bundle_analysis_javascript_size: AssetType.JAVASCRIPT,
                }
                for measurement_name, asset_type in asset_type_map.items():
                    if measurement_name.value in dataset_names:
                        total_size = 0
                        for asset in bundle_report.asset_reports():
                            if asset.asset_type == asset_type:
                                total_size += asset.size
                        self._save_to_timeseries(
                            db_session,
                            commit,
                            measurement_name.value,
                            bundle_report.name,
                            total_size,
                        )

            return ProcessingResult(
                upload=upload,
                commit=commit,
            )
        except Exception:
            sentry_metrics.incr(
                "bundle_analysis_upload",
                tags={
                    "result": "parser_error",
                    "repository": commit.repository.repoid,
                },
            )
            return ProcessingResult(
                upload=upload,
                commit=commit,
                error=ProcessingError(
                    code="measurement_save_error",
                    params={
                        "location": upload.storage_path,
                        "repository": commit.repository.repoid,
                    },
                    is_retryable=False,
                ),
            )
