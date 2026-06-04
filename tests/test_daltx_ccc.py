import json
from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD

from city_scrapers.spiders.daltx_ccc import DaltxCccSpider


@pytest.fixture
def spider():
    return DaltxCccSpider()


@pytest.fixture
def meeting_item():
    with open(
        join(dirname(__file__), "files", "daltx_ccc_meeting_info.json"),
        encoding="utf-8",
    ) as f:
        return json.load(f)[0]


@pytest.fixture
def links_data():
    with open(
        join(dirname(__file__), "files", "daltx_ccc_links.json"), encoding="utf-8"
    ) as f:
        return json.load(f)


@pytest.fixture
def court_order_data():
    with open(
        join(dirname(__file__), "files", "daltx_ccc_court_order.json"), encoding="utf-8"
    ) as f:
        return json.load(f)[0]


@pytest.fixture
def document_links(spider, links_data):
    return spider._parse_document_links(links_data)


def test_title(spider, meeting_item):
    assert spider._parse_title(meeting_item) == "Commissioners Court"


def test_classification(spider):
    assert spider._parse_classification("Commissioners Court") == BOARD


def test_start(spider, meeting_item):
    assert spider._parse_start(meeting_item) == datetime(2026, 5, 19, 9, 0)


def test_time_notes(spider, meeting_item):
    start = spider._parse_start(meeting_item)
    assert spider._parse_time_notes(start) == ""


def test_location(spider, meeting_item):
    assert spider._parse_location(meeting_item) == {
        "name": "Commissioners Court Room",
        "address": "500 Elm Street, Dallas, TX 75202",
    }


def test_document_links_count(document_links):
    assert len(document_links) == 4


def test_agenda_link(document_links):
    assert {
        "href": "https://dallascounty.civicweb.net/document/1051671/?printPdf=true",
        "title": "Agenda",
    } in document_links


def test_agenda_packet_link(document_links):
    assert {
        "href": "https://dallascounty.civicweb.net/document/1051670/Commissioners%20Court%20-%20May%2019%202026.pdf",  # noqa
        "title": "Agenda Packet",
    } in document_links


def test_minutes_link(document_links):
    assert {
        "href": "https://dallascounty.civicweb.net/document/1051860/?printPdf=true",
        "title": "Minutes",
    } in document_links


def test_minutes_packet_link(document_links):
    assert {
        "href": "https://dallascounty.civicweb.net/document/1051859/Commissioners%20Court%20-%20May%2019%202026.pdf",  # noqa
        "title": "Minutes Packet",
    } in document_links


def test_court_order_url(court_order_data):
    assert (
        court_order_data.get("MeetingExternalLinkUrl")
        == "https://dallascounty.civicweb.net/document/1045411"
    )


def test_court_order_name(court_order_data):
    assert court_order_data.get("MeetingExternalLinkName") == "APPROVED COURT ORDERS"
