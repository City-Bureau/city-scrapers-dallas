from datetime import datetime
from os.path import dirname, join

from city_scrapers_core.constants import CANCELLED
from freezegun import freeze_time
from scrapy.http import TextResponse

from city_scrapers.spiders.daltx_school_district import DaltxSchoolDistrictSpider

freezer = freeze_time("2026-05-13")
freezer.start()

with open(
    join(dirname(__file__), "files", "daltx_school_district.json"),
    "r",
    encoding="utf-8",
) as f:
    test_data = f.read()

with open(
    join(dirname(__file__), "files", "daltx_school_district_docs.json"), "rb"
) as f:
    docs_data = f.read()

with open(
    join(dirname(__file__), "files", "daltx_school_district_video.json"), "rb"
) as f:
    video_data = f.read()

spider = DaltxSchoolDistrictSpider()
test_response = TextResponse(
    url=(
        "https://dallasisd.community.highbond.com"
        "/Services/MeetingsService.svc/meetings"
        "?from=2025-05-01&to=9999-12-31&loadall=true"
    ),
    body=test_data.encode("utf-8"),
)
docs_response = TextResponse(
    url=(
        "https://dallasisd.community.highbond.com"
        "/Services/MeetingsService.svc/meetings/826/meetingDocuments?_=0"
    ),
    body=docs_data,
)
video_response = TextResponse(
    url=(
        "https://dallasisd.community.highbond.com"
        "/Services/MeetingsService.svc/meetings/826/meetingData?_=0"
    ),
    body=video_data,
)

parse_requests = list(spider.parse(test_response))

# Intermediate meeting objects before document/video fetch
intermediate_items = [req.cb_kwargs["meeting"] for req in parse_requests]

# Simulate the full chain for the first meeting (Id=826)
first_doc_req = parse_requests[0]
video_requests = list(first_doc_req.callback(docs_response, **first_doc_req.cb_kwargs))
parsed_first = list(
    video_requests[0].callback(video_response, **video_requests[0].cb_kwargs)
)

# Simulate the full chain for the cancelled/midnight meeting (index 17, Id=755)
cancelled_docs_response = TextResponse(
    url=(
        "https://dallasisd.community.highbond.com"
        "/Services/MeetingsService.svc/meetings/755/meetingDocuments?_=0"
    ),
    body=b'{"Documents":[],"MeetingDateFormatted":"Feb 18, 2026"}',
)
cancelled_video_response = TextResponse(
    url=(
        "https://dallasisd.community.highbond.com"
        "/Services/MeetingsService.svc/meetings/755/meetingData?_=0"
    ),
    body=b'{"MeetingExternalLinkUrl": ""}',
)
cancelled_doc_req = parse_requests[17]
cancelled_video_reqs = list(
    cancelled_doc_req.callback(cancelled_docs_response, **cancelled_doc_req.cb_kwargs)
)
parsed_cancelled = list(
    cancelled_video_reqs[0].callback(
        cancelled_video_response, **cancelled_video_reqs[0].cb_kwargs
    )
)

freezer.stop()


def test_count():
    assert len(parse_requests) == 50


def test_title():
    assert intermediate_items[0]["title"] == "Public Hearing Agenda and Notice"


def test_start():
    assert intermediate_items[0]["start"] == datetime(2026, 5, 28, 17, 30)


def test_end():
    assert intermediate_items[0]["end"] is None


def test_location():
    assert intermediate_items[0]["location"] == {
        "name": "Ada L. Williams Governance Room",
        "address": "5151 Samuell Blvd., Dallas, TX 75228",
    }


def test_classification():
    assert intermediate_items[0]["classification"] == "Board"  # Public Hearing
    assert intermediate_items[1]["classification"] == "Board"  # Board Meeting


def test_status():
    assert parsed_first[0]["status"] == "tentative"


def test_links():
    assert parsed_first[0]["links"] == [
        {
            "href": (
                "https://dallasisd.community.highbond.com"
                "/document/49668"
                "/Public%20Hearing%20Agenda%20and%20Notice%20%20-%20May%2028%202026.pdf"
            ),
            "title": "Agenda",
        },
        {
            "href": "https://dallasisdtx.new.swagit.com/videos/384412",
            "title": "Video",
        },
    ]


def test_source():
    assert intermediate_items[0]["source"] == (
        "https://dallasisd.community.highbond.com/Portal/MeetingSchedule.aspx"
    )


def test_id():
    assert (
        parsed_first[0]["id"]
        == "daltx_school_district/202605281730/x/public_hearing_agenda_and_notice"
    )


def test_all_day():
    assert intermediate_items[0]["all_day"] is False


def test_location_known_room():
    assert intermediate_items[2]["location"] == {
        "name": "Theater Room",
        "address": "5151 Samuell Blvd., Dallas, TX 75228",
    }


def test_location_empty():
    assert intermediate_items[17]["location"] == {"name": "", "address": ""}


def test_location_split():
    result = spider._parse_location(
        {
            "MeetingLocation": (
                "Linus D Wright Dallas ISD Administration Bldg"
                " 9400 N. Central Expressway Dallas, TX 75231"
            )
        }
    )
    assert result == {
        "name": "Linus D Wright Dallas ISD Administration Bldg",
        "address": "9400 N. Central Expressway Dallas, TX 75231",
    }


def test_time_notes():
    assert intermediate_items[17]["time_notes"] == (
        "See source website for meeting time"
    )
    assert intermediate_items[0]["time_notes"] == ""


def test_cancelled():
    assert parsed_cancelled[0]["status"] == CANCELLED
