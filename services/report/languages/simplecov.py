import typing

from shared.reports.resources import Report, ReportFile
from shared.reports.types import ReportLine

from services.report.languages.base import BaseLanguageProcessor
from services.report.report_builder import ReportBuilder, ReportBuilderSession


class SimplecovProcessor(BaseLanguageProcessor):
    """
    Handles processing of coverage reports generated by Simplecov (https://github.com/simplecov-ruby/simplecov)
    The JSON formatter this processor expects is simplecov-json (https://github.com/vicentllongo/simplecov-json)

    """

    def matches_content(self, content, first_line, name):
        return isinstance(content, dict) and content.get("command_name") == "RSpec"

    def process(
        self, name: str, content: typing.Any, report_builder: ReportBuilder
    ) -> Report:
        report_builder_session = report_builder.create_report_builder_session(name)
        return from_json(content, report_builder_session)


def from_json(json, report_builder_session: ReportBuilderSession) -> Report:
    fix, ignored_lines, sessionid = (
        report_builder_session.path_fixer,
        report_builder_session.ignored_lines,
        report_builder_session.sessionid,
    )
    for data in json["files"]:
        fn = fix(data["filename"])
        if fn is None:
            continue

        _file = ReportFile(fn, ignore=ignored_lines.get(fn))

        # Structure depends on which Simplecov version was used so we need to handle either structure
        coverage = data["coverage"]
        coverage_to_check = (
            coverage["lines"]
            if isinstance(coverage, dict)
            and coverage.get("lines")  # Simplecov version >= 0.18
            else coverage  # Simplecov version < 0.18
        )

        for ln, cov in enumerate(coverage_to_check, start=1):
            _file[ln] = ReportLine.create(coverage=cov, sessions=[[sessionid, cov]])

        report_builder_session.append(_file)

    return report_builder_session.output_report()
