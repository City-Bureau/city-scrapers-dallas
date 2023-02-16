import json
from datetime import datetime
from os.path import dirname, join

from freezegun import freeze_time

from city_scrapers.spiders.daltx_city_council import DaltxCityCouncilSpider

freezer = freeze_time("2023-02-10")
freezer.start()

with open(
    join(dirname(__file__), "files", "daltx_city_council.json"), "r", encoding="utf-8"
) as f:
    test_response = json.load(f)

spider = DaltxCityCouncilSpider()
parsed_items = [item for item in spider.parse_legistar(test_response)]

freezer.stop()


"""
Uncomment below
def test_tests():
    print("Please write some tests for this spider or at least disable this one.")
    assert False

"""


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "COUNCIL BRIEFING ROOM, 6ES",
        "address": "1500 Marilla Street Dallas, TX 75201",
    }


def test_title():
    assert parsed_items[0]["title"] == "Municipal Library Board"


# def test_description():
#     assert parsed_items[0]["description"] == "EXPECTED DESCRIPTION"


def test_start():
    assert parsed_items[0]["start"] == datetime(2023, 2, 28, 16, 0)


# def test_end():
#     assert parsed_items[0]["end"] == datetime(2019, 1, 1, 0, 0)


# def test_time_notes():
#     assert parsed_items[0]["time_notes"] == "EXPECTED TIME NOTES"


def test_id():
    assert (
        parsed_items[0]["id"]
        == "daltx_city_council/202302281600/x/municipal_library_board"
    )


def test_status():
    assert parsed_items[0]["status"] == "tentative"


def test_source():
    assert (
        parsed_items[0]["source"] == "https://cityofdallas.legistar.com/Calendar.aspx"
    )


# def test_links():
#     assert parsed_items[0]["links"] == [{
#       "href": "EXPECTED HREF",
#       "title": "EXPECTED TITLE"
#     }]


def test_classification():
    assert parsed_items[0]["classification"] == "City Council"


# @pytest.mark.parametrize("item", parsed_items)
# def test_all_day(item):
#     assert item["all_day"] is False


# @pytest.mark.parametrize("item", parsed_items)
# def test_all_day(item):
#     assert item["all_day"] is False
