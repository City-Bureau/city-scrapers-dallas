from datetime import datetime
from os.path import dirname, join

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

spider = DaltxSchoolDistrictSpider()
test_response = TextResponse(
    url=(
        "https://dallasisd.community.highbond.com"
        "/Services/MeetingsService.svc/meetings"
        "?from=2025-05-01&to=9999-12-31&loadall=true"
    ),
    body=test_data.encode("utf-8"),
)
parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 50


def test_title():
    assert parsed_items[0]["title"] == "Public Hearing Agenda and Notice"


def test_start():
    assert parsed_items[0]["start"] == datetime(2026, 5, 28, 17, 30)


def test_end():
    assert parsed_items[0]["end"] is None


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "Ada L. Williams Governance Room",
        "address": "5151 Samuell Blvd., Dallas, TX 75228",
    }


def test_classification():
    assert parsed_items[0]["classification"] == "Not classified"
    assert parsed_items[1]["classification"] == "Board"


def test_status():
    assert parsed_items[0]["status"] == "tentative"


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": (
                "https://dallasisd.community.highbond.com"
                "/Portal/MeetingInformation.aspx?Org=Cal&Id=826"
            ),
            "title": "Meeting Details",
        }
    ]


def test_source():
    assert parsed_items[0]["source"] == (
        "https://dallasisd.community.highbond.com/Portal/MeetingSchedule.aspx"
    )


def test_id():
    assert (
        parsed_items[0]["id"]
        == "daltx_school_district/202605281730/x/public_hearing_agenda_and_notice"
    )


def test_all_day():
    assert parsed_items[0]["all_day"] is False
