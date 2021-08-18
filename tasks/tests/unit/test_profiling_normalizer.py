import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from shared.storage.exceptions import FileNotInStorageError

from database.tests.factories.profiling import (
    ProfilingCommitFactory,
    ProfilingUploadFactory,
)
from tasks.profiling_normalizer import ProfilingNormalizerTask

here = Path(__file__)


@pytest.fixture
def sample_open_telemetry_upload():
    with open(here.parent / "samples/sample_opentelem_input.json", "r") as file:
        return json.load(file)


@pytest.mark.asyncio
async def test_run_async_simple_normalizing_run(
    dbsession,
    mock_storage,
    mock_configuration,
    mock_redis,
    mocker,
    sample_open_telemetry_upload,
):
    puf = ProfilingUploadFactory.create(
        profiling_commit__repository__yaml={"codecov": {"max_report_age": None}},
        raw_upload_location="raw_upload_location",
    )
    mock_configuration._params["services"]["minio"]["bucket"] = "bucket"
    mock_storage.write_file(
        "bucket", "raw_upload_location", json.dumps(sample_open_telemetry_upload),
    )
    dbsession.add(puf)
    dbsession.flush()
    task = ProfilingNormalizerTask()
    res = await task.run_async(dbsession, profiling_upload_id=puf.id)
    assert res["successful"]
    assert json.loads(mock_storage.read_file("bucket", res["location"]).decode()) == {
        "files": {
            "codecov_auth/models.py": {
                "1": 0,
                "2": 0,
                "3": 0,
                "4": 0,
                "5": 0,
                "6": 0,
                "8": 0,
                "9": 0,
                "10": 0,
                "11": 0,
                "13": 0,
                "14": 0,
                "15": 0,
                "17": 0,
                "26": 0,
                "29": 0,
                "31": 0,
                "32": 0,
                "33": 0,
                "34": 0,
                "35": 0,
                "36": 0,
                "39": 0,
                "42": 0,
                "46": 0,
                "47": 0,
                "48": 0,
                "49": 0,
                "50": 0,
                "51": 0,
                "52": 0,
                "55": 0,
                "56": 0,
                "59": 0,
                "60": 0,
                "61": 0,
                "62": 0,
                "63": 0,
                "72": 0,
                "73": 0,
                "75": 0,
                "76": 0,
                "77": 0,
                "80": 0,
                "81": 0,
                "82": 0,
                "83": 0,
                "84": 0,
                "88": 0,
                "90": 0,
                "91": 0,
                "92": 0,
                "93": 0,
                "94": 0,
                "95": 0,
                "96": 0,
                "97": 0,
                "100": 0,
                "101": 0,
                "102": 0,
                "103": 0,
                "104": 0,
                "105": 0,
                "106": 0,
                "107": 0,
                "108": 0,
                "109": 0,
                "110": 0,
                "111": 0,
                "112": 0,
                "113": 0,
                "116": 0,
                "117": 0,
                "118": 0,
                "120": 0,
                "122": 0,
                "124": 0,
                "125": 0,
                "126": 0,
                "128": 0,
                "130": 0,
                "132": 0,
                "134": 0,
                "136": 0,
                "140": 0,
                "141": 0,
                "142": 0,
                "143": 0,
                "144": 0,
                "145": 0,
                "146": 0,
                "148": 0,
                "150": 0,
                "156": 0,
                "157": 0,
                "161": 0,
                "162": 0,
                "163": 0,
                "164": 0,
                "165": 0,
                "168": 0,
                "169": 0,
                "170": 0,
                "172": 0,
                "174": 0,
                "176": 0,
                "180": 0,
                "181": 0,
                "182": 0,
                "184": 0,
                "186": 0,
                "187": 0,
                "188": 0,
                "190": 0,
                "192": 0,
                "196": 0,
                "198": 0,
                "199": 0,
                "200": 0,
                "204": 0,
                "206": 0,
                "207": 0,
                "208": 0,
                "212": 0,
                "214": 0,
                "216": 0,
                "218": 0,
                "223": 0,
                "224": 0,
                "228": 0,
                "229": 1,
                "231": 0,
                "234": 2,
                "236": 0,
                "239": 0,
                "241": 0,
                "244": 1,
                "246": 0,
                "249": 1,
                "251": 0,
                "254": 1,
                "256": 0,
                "259": 0,
                "261": 0,
                "264": 1,
                "266": 0,
                "267": 0,
                "268": 0,
                "269": 0,
                "273": 0,
                "274": 0,
                "279": 0,
                "280": 0,
                "284": 0,
                "289": 0,
                "290": 0,
                "294": 0,
                "299": 0,
                "300": 0,
                "303": 0,
                "304": 0,
                "308": 0,
                "309": 0,
                "313": 0,
                "314": 0,
                "318": 0,
                "319": 0,
                "324": 0,
                "328": 0,
                "330": 0,
                "331": 0,
                "338": 0,
                "339": 0,
                "341": 0,
                "342": 0,
                "346": 0,
                "347": 0,
                "348": 0,
                "349": 0,
                "350": 0,
                "352": 0,
                "353": 0,
                "355": 0,
                "356": 0,
                "357": 0,
                "358": 0,
                "359": 0,
                "360": 0,
                "361": 0,
                "362": 0,
                "364": 0,
                "365": 0,
                "368": 0,
                "369": 0,
                "370": 0,
                "372": 0,
                "373": 0,
                "375": 0,
                "376": 0,
                "379": 0,
                "380": 0,
                "381": 0,
                "382": 0,
                "383": 0,
                "384": 0,
                "386": 0,
                "387": 0,
                "388": 0,
                "389": 0,
                "390": 0,
                "391": 0,
                "392": 0,
                "395": 0,
                "396": 0,
                "402": 0,
                "403": 0,
                "404": 0,
                "406": 0,
                "408": 0,
                "411": 0,
                "412": 0,
                "413": 0,
                "414": 0,
                "416": 0,
                "417": 0,
                "418": 0,
                "420": 0,
                "421": 0,
                "422": 0,
                "423": 0,
                "424": 0,
                "425": 0,
                "426": 0,
                "427": 0,
            },
            "codecov_auth/authentication/__init__.py": {
                "1": 0,
                "2": 0,
                "3": 0,
                "4": 0,
                "5": 0,
                "6": 0,
                "8": 0,
                "9": 0,
                "10": 0,
                "12": 0,
                "13": 0,
                "14": 0,
                "15": 0,
                "17": 0,
                "20": 0,
                "21": 0,
                "22": 0,
                "23": 0,
                "24": 0,
                "25": 0,
                "26": 0,
                "28": 0,
                "29": 0,
                "31": 0,
                "32": 0,
                "33": 0,
                "34": 0,
                "35": 0,
                "36": 0,
                "40": 0,
                "46": 0,
                "47": 0,
                "49": 0,
                "50": 0,
                "56": 0,
                "57": 0,
                "58": 0,
                "59": 0,
                "61": 0,
                "62": 0,
                "65": 0,
                "66": 0,
                "72": 0,
                "75": 0,
                "81": 0,
                "83": 0,
                "84": 0,
                "85": 0,
                "88": 0,
                "89": 0,
                "90": 1,
                "91": 1,
                "93": 1,
                "94": 1,
                "96": 0,
                "98": 0,
                "101": 0,
                "102": 0,
                "103": 2,
                "106": 0,
                "109": 0,
                "110": 0,
                "113": 0,
                "151": 0,
                "152": 0,
                "153": 0,
                "155": 0,
                "156": 0,
                "158": 0,
                "160": 0,
                "161": 0,
            },
            "codecov_auth/admin.py": {
                "1": 0,
                "2": 0,
                "3": 0,
                "5": 0,
                "6": 0,
                "9": 0,
                "10": 0,
                "11": 0,
                "14": 0,
                "16": 0,
                "17": 0,
                "20": 0,
                "26": 0,
                "29": 0,
                "32": 0,
                "33": 0,
                "34": 0,
                "35": 0,
                "36": 0,
                "37": 0,
                "38": 0,
                "40": 0,
                "41": 0,
                "46": 0,
                "47": 0,
                "49": 0,
                "50": 1,
                "52": 0,
                "53": 1,
                "56": 0,
            },
            "compare/admin.py": {
                "1": 0,
                "3": 0,
                "6": 0,
                "7": 0,
                "8": 0,
                "17": 0,
                "18": 0,
                "20": 0,
                "22": 0,
                "23": 0,
                "25": 0,
                "27": 0,
                "28": 0,
                "30": 0,
                "32": 0,
                "33": 0,
                "34": 0,
                "38": 0,
                "39": 1,
                "41": 0,
                "42": 1,
            },
        }
    }


@pytest.mark.asyncio
async def test_run_sync_normalizing_run_no_file(
    dbsession, mock_storage, mock_configuration
):
    puf = ProfilingUploadFactory.create(
        profiling_commit__repository__yaml={"codecov": {"max_report_age": None}},
        raw_upload_location="raw_upload_location",
    )
    mock_configuration._params["services"]["minio"]["bucket"] = "bucket"
    dbsession.add(puf)
    dbsession.flush()
    task = ProfilingNormalizerTask()
    res = await task.run_async(dbsession, profiling_upload_id=puf.id)
    assert res == {"successful": False}
