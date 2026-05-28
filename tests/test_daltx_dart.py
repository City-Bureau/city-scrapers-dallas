from datetime import datetime
from os.path import dirname, join

import pytest
import scrapy
from city_scrapers_core.constants import BOARD, COMMITTEE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.daltx_dart import DaltxDartSpider


@pytest.fixture(scope="module")
def parsed_items():
    spider = DaltxDartSpider()

    # Parse the upcoming and current board meetings page
    upcoming_response = file_response(
        join(dirname(__file__), "files", "daltx_dart.html"),
        url="https://www.dart.org/about/public-access-information/board-meetings-information",  # noqa
    )

    with freeze_time("2026-05-21"):
        return [
            item
            for item in spider.parse(upcoming_response)
            if not isinstance(item, scrapy.Request)
        ]


@pytest.fixture(scope="module")
def parsed_archive_items():
    spider = DaltxDartSpider()

    archive_response = file_response(
        join(dirname(__file__), "files", "daltx_dart_archive.html"),
        url=(
            "https://www.dart.org/about/public-access-information/"
            "board-meetings-information/board-meetings-agenda-and-minutes-archive/-page-1-"  # noqa
        ),
    )

    with freeze_time("2026-05-21"):
        return list(
            spider._yield_meetings_from_rows(
                spider._extract_js_array(archive_response.text, "var data"),
                archive_response.url,
            )
        )


#  Upcoming and currrent meetings page tests
def test_no_duplicates(parsed_items):
    """No two meetings should share the exact same (start, title)."""
    seen = set()
    for item in parsed_items:
        key = (item["start"], item["title"])
        assert key not in seen, f"Duplicate meeting: {key}"
        seen.add(key)


def test_title(parsed_items):
    assert (
        parsed_items[0]["title"]
        == "DART NOTICE of Possible Quorum at Dallas City Council Transportation and Infrastructure Committee Meeting"  # noqa: E501
    )


def test_description(parsed_items):
    for item in parsed_items:
        assert item["description"] == (
            "The DART Board of Directors meetings convene at 6:00 p.m. on the fourth Tuesday "  # noqa
            "of each month, unless specified differently on the calendar. Standing Committee "  # noqa
            "meetings are generally held on the second Tuesday of each month. *July, November, "  # noqa
            "and December have one meeting date only. Meeting dates are subject to change."  # noqa
        )


def test_start_is_datetime(parsed_items):
    assert parsed_items[0]["start"] == datetime(2026, 5, 18, 13, 0)


def test_end_is_none(parsed_items):
    """Spider does not parse end times."""
    for item in parsed_items:
        assert item["end"] is None


def test_all_day(parsed_items):
    for item in parsed_items:
        assert item["all_day"] is False


def test_time_notes(parsed_items):
    for item in parsed_items:
        assert item["time_notes"] == ""


def test_location(parsed_items):
    for item in parsed_items:
        assert item["location"] == {
            "name": "DART Headquarters, Board Room",
            "address": "1401 Pacific Ave, Dallas, TX 75202",
        }


def test_source(parsed_items):
    assert (
        parsed_items[0]["source"]
        == "https://www.dart.org/about/public-access-information/board-meetings-information"  # noqa: E501
    )


def test_id(parsed_items):
    assert (
        parsed_items[0]["id"]
        == "daltx_dart/202605181300/x/dart_notice_of_possible_quorum_at_dallas_city_council_transportation_and_infrastructure_committee_meeting"  # noqa
    )


def test_status(parsed_items):
    valid_statuses = {"passed", "tentative", "cancelled"}
    for item in parsed_items:
        assert item["status"] in valid_statuses


def test_meeting_status(parsed_items):
    assert parsed_items[0]["status"] == "passed"


#  Classification tests
def test_board_classification(parsed_items):
    board_items = [i for i in parsed_items if "board" in i["title"].lower()]
    for item in board_items:
        assert item["classification"] == BOARD


def test_committee_classification(parsed_items):
    committee_items = [
        i
        for i in parsed_items
        if "committee" in i["title"].lower() and "board" not in i["title"].lower()
    ]
    for item in committee_items:
        assert item["classification"] == COMMITTEE


#  Links tests
def test_links_are_list(parsed_items):
    for item in parsed_items:
        assert isinstance(item["links"], list)


def test_links_have_href_and_title(parsed_items):
    for item in parsed_items:
        for link in item["links"]:
            assert "href" in link
            assert "title" in link


def test_meeting_links(parsed_items):
    assert parsed_items[0]["links"] == [
        {
            "href": "https://dartorgcmsblob.dart.org/prod/docs/default-source/about-dart/2026-05-18-trni-dart-quorum-notice.pdf?sfvrsn=dc309df8_1",  # noqa
            "title": "2026-05-18 TRNI-DART Quorum Notice",
        },
    ]


#  Date range tests
def test_cutoff_date(parsed_items):
    """No meetings should be older than current year - 3."""
    from datetime import datetime

    cutoff = datetime(datetime.now().year - 3, 1, 1)
    for item in parsed_items:
        assert (
            item["start"] >= cutoff
        ), f"Meeting {item['title']} at {item['start']} is before cutoff {cutoff}"  # noqa


#  Title normalization tests
def test_no_date_prefix_in_title(parsed_items):
    """Titles should not start with a date like '2026-05-12 '."""
    for item in parsed_items:
        assert not item["title"].startswith(
            tuple("0123456789")
        ), f"Title has leading date: {item['title']}"


#  _norm_title unit tests
@pytest.fixture(scope="module")
def spider():
    return DaltxDartSpider()


def test_norm_title_treac(spider):
    result = spider._norm_title("TREAC Meeting")
    assert "trinity railway express advisory committee" in result


def test_norm_title_trinity_railway(spider):
    result = spider._norm_title("Trinity Railway Advisory Committee Meeting")
    assert "trinity railway express advisory committee" in result


def test_norm_title_tre(spider):
    result = spider._norm_title("TRE Advisory Committee Meeting")
    assert "trinity railway express advisory committee" in result
