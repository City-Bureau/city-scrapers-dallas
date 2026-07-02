from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.daltx_bot import DaltxBotSpider

events_page = file_response(
    join(dirname(__file__), "files", "daltx_bot.html"),
    url="https://www.dallascollege.edu/events/?categories%5B%5D=Category%3EBoard%20of%20Trustees&search=all",  # noqa
)

details_page = file_response(
    join(dirname(__file__), "files", "daltx_bot_details_page_example.html"),
    url="https://www.dallascollege.edu/events/trustees/2026/jun-2-board-meeting---regular/",  # noqa
)


@pytest.fixture
def spider():
    return DaltxBotSpider()


@pytest.fixture
def request_items(spider):
    with freeze_time("2026-05-13"):
        return [request for request in spider.parse(events_page)]


@pytest.fixture
def parsed_item(spider):
    item = events_page.css(".row.calendar-search-results")[0]
    details_page.request.meta["item"] = item
    with freeze_time("2026-05-13"):
        return next(spider._construct_meeting(details_page))


def test_count(request_items):
    assert len(request_items) == 2


def test_title(parsed_item):
    assert parsed_item["title"] == "June Board Meeting - Regular"


def test_description(parsed_item):
    assert (
        parsed_item["description"]
        == "The Board of Trustees will hold a regular meeting on June 2, 2026."
    )


def test_start(parsed_item):
    assert parsed_item["start"] == datetime(2026, 6, 2, 16, 0)


def test_end(parsed_item):
    assert parsed_item["end"] == datetime(2026, 6, 2, 17, 0)


def test_time_notes(parsed_item):
    assert parsed_item["time_notes"] == ""


def test_id(parsed_item):
    assert (
        parsed_item["id"]
        == "daltx_bot/202606021600/x/june_board_meeting_regular"  # noqa
    )


def test_status(parsed_item):
    assert parsed_item["status"] == TENTATIVE


def test_location(parsed_item):
    assert parsed_item["location"] == {
        "name": "Administrative Office",
        "address": "1601 Botham Jean Blvd., Dallas TX 75215",
    }


def test_source(parsed_item):
    assert (
        parsed_item["source"]
        == "https://www.dallascollege.edu/events/trustees/2026/jun-2-board-meeting---regular/"  # noqa
    )


def test_links(parsed_item):
    assert parsed_item["links"] == [
        {
            "href": "https://www.dallascollege.edu/events/trustees/2026/jun-2-board-meeting---regular/",  # noqa
            "title": "Meeting Details",
        },
    ]


def test_classification(parsed_item):
    assert parsed_item["classification"] == BOARD
