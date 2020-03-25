from time import time
import xml.etree.cElementTree as etree
import pytest

from tests.base import BaseTestCase
from helpers.exceptions import ReportExpiredException
from services.report.languages import cobertura

xml = '''<?xml version="1.0" ?>
<!DOCTYPE coverage
  SYSTEM 'http://cobertura.sourceforge.net/xml/coverage-03.dtd'>
<%scoverage branch-rate="0.07143" line-rate="0.5506" timestamp="%s" version="3.7.1">
    <!-- Generated by coverage.py: http://nedbatchelder.com/code/coverage -->
    <packages>
        <package branch-rate="0.07143" complexity="0" line-rate="0.5506" name="">
            <classes>
                <class branch-rate="0.07143" complexity="0" filename="empty" line-rate="0.5506" name="empty/src"></class>
                <class branch-rate="0.07143" complexity="0" filename="source" line-rate="0.5506" name="folder/file">
                    <methods>
                        <method name="(anonymous_1)"  hits="1"  signature="()V" >
                            <lines><line number="undefined"  hits="1" /></lines>
                        </method>
                    </methods>
                    <lines>
                        <line hits="8" number="0"/>
                        <line hits="1.0" number="1"/>
                        <line branch="true" condition-coverage="0%% (0/2)" hits="1" missing-branches="exit" number="2"/>
                        <line branch="true" condition-coverage="50%% (1/2)" hits="1" missing-branches="30" number="3"/>
                        <line branch="true" condition-coverage="100%% (2/2)" hits="1" number="4"/>
                        <line number="5" hits="0" branch="true" condition-coverage="50%% (2/4)">
                          <conditions>
                            <condition number="0" type="jump" coverage="0%%"/>
                            <condition number="1" type="jump" coverage="0%%"/>
                            <condition number="2" type="jump" coverage="100%%"/>
                            <condition number="3" type="jump" coverage="100%%"/>
                          </conditions>
                        </line>
                        <line number="6" hits="0" branch="true" condition-coverage="50%% (2/4)">
                          <conditions>
                            <condition number="0" type="jump" coverage="0%%"/>
                            <condition number="1" type="jump" coverage="0%%"/>
                          </conditions>
                        </line>
                        <line branch="true" condition-coverage="0%% (0/2)" hits="1" missing-branches="exit,exit,exit" number="7"/>
                        <line branch="true" condition-coverage="50%%" hits="1" number="8"/>
                    </lines>
                </class>
                <!-- Scala coverage -->
                <class branch-rate="0.07143" complexity="0" filename="file" line-rate="0.5506" name="">
                    <methods>
                        <statements>
                            <statement source="file" method="beforeInteropCommit" line="1" branch="false" invocation-count="0"></statement>
                            <statement source="file" method="" line="2" branch="true" invocation-count="1"></statement>
                            <statement source="file" method="" line="3" branch="false" invocation-count="1"></statement>
                        </statements>
                    </methods>
                </class>
                <class branch-rate="0.07143" complexity="0" filename="ignore" line-rate="0.5506" name="codecov/__init__"></class>
            </classes>
        </package>
    </packages>
</%scoverage>
'''


class TestCobertura(BaseTestCase):
    def test_report(self):
        def fixes(path):
            if path == 'ignore':
                return None
            assert path in ('source', 'empty', 'file', 'nolines')
            return path

        report = cobertura.from_xml(etree.fromstring(xml % ('', int(time()), '')), fixes, {}, 0, {'codecov': {'max_report_age': None}})
        processed_report = self.convert_report_to_better_readable(report)
        import pprint
        pprint.pprint(processed_report)
        expected_result = {
            'archive': {
                'file': [
                    (1, 0, 'm', [[0, 0]], None, None),
                    (2, 1, 'b', [[0, 1]], None, None),
                    (3, 1, None, [[0, 1]], None, None)
                ],
                'source': [
                    (1, 1, None, [[0, 1]], None, None),
                    (2, '0/2', 'b', [[0, '0/2', ['exit']]], None, None),
                    (3, '1/2', 'b', [[0, '1/2', ['30']]], None, None),
                    (4, '2/2', 'b', [[0, '2/2']], None, None),
                    (5, '2/4', 'b', [[0, '2/4', ['0:jump', '1:jump']]], None, None),
                    (6, '2/4', 'b', [[0, '2/4', ['0:jump', '1:jump']]], None, None),
                    (7, '0/2', 'b', [[0, '0/2', ['loop', 'exit']]], None, None),
                    (8, 1, None, [[0, 1]], None, None)
                ]
            },
            'report': {
                'files': {
                    'file': [
                        1,
                        [0, 3, 2, 1, 0, '66.66667', 1, 1, 0, 0, 0, 0, 0],
                        [[0, 3, 2, 1, 0, '66.66667', 1, 1, 0, 0, 0, 0, 0]],
                        None
                    ],
                    'source': [
                        0,
                        [0, 8, 3, 2, 3, '37.50000', 6, 0, 0, 0, 0, 0, 0],
                        [[0, 8, 3, 2, 3, '37.50000', 6, 0, 0, 0, 0, 0, 0]],
                        None
                    ]
                },
                'sessions': {}
            },
            'totals': {
                'C': 0,
                'M': 0,
                'N': 0,
                'b': 7,
                'c': '45.45455',
                'd': 1,
                'diff': None,
                'f': 2,
                'h': 5,
                'm': 3,
                'n': 11,
                'p': 3,
                's': 0
            }
        }
        assert processed_report == expected_result

    def test_timestamp_zero_passes(self):
        # Some reports have timestamp as a string zero, check we can handle that
        timestring = "0"
        report = cobertura.from_xml(etree.fromstring(xml % ('', timestring, '')), lambda path: path, {}, 0, {'codecov': {'max_report_age': "12h"}})
        processed_report = self.convert_report_to_better_readable(report)
        assert len(processed_report["archive"]["file"]) == 3
        assert processed_report["totals"]["c"] == "45.45455"

    @pytest.mark.parametrize("date", [(int(time()) - 172800), '01-01-2014'])
    def test_expired(self, date):
        with pytest.raises(ReportExpiredException, match='Cobertura report expired'):
            cobertura.from_xml(etree.fromstring(xml % ('', date, '')), None, {}, None, None)

        with pytest.raises(ReportExpiredException, match='Cobertura report expired'):
            cobertura.from_xml(etree.fromstring(xml % ('s', date, 's')), None, {}, None, None)

    def test_matches_content(self):
        processor = cobertura.CoberturaProcessor()
        content = etree.fromstring(xml % ('', int(time()), ''))
        first_line = xml.split("\n", 1)[0]
        name = "coverage.xml"
        assert processor.matches_content(content, first_line, name)

    def test_not_matches_content(self):
        processor = cobertura.CoberturaProcessor()
        content = etree.fromstring("""<?xml version="1.0" standalone="yes"?>
            <CoverageDSPriv>
              <Lines>
                <LnStart>258</LnStart>
                <ColStart>0</ColStart>
                <LnEnd>258</LnEnd>
                <ColEnd>0</ColEnd>
                <Coverage>1</Coverage>
                <SourceFileID>1</SourceFileID>
                <LineID>0</LineID>
              </Lines>
            </CoverageDSPriv>""")
        first_line = xml.split("\n", 1)[0]
        name = "coverage.xml"
        assert not processor.matches_content(content, first_line, name)

