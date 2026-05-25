from datetime import datetime

from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse as date_parser


class DaltxBotSpider(CityScrapersSpider):
    name = "daltx_bot"
    agency = "Dallas College Board of Trustees"
    timezone = "America/Chicago"
    start_urls = [
        "https://www.dallascollege.edu/events/?categories%5B%5D=Category%3EBoard%20of%20Trustees&search=all"  # noqa
    ]

    def parse(self, response):
        records = response.css(".row.calendar-search-results")

        for item in records:
            detail_url = item.css("h4.cal-header a::attr(href)").get()
            if not detail_url:
                continue

            yield response.follow(
                url=response.urljoin(detail_url),
                callback=self._construct_meeting,
                meta={"item": item},
            )

    def _construct_meeting(self, response):
        item = response.meta["item"]

        start, end, all_day = self._parse_datetime(item)
        location, time_notes = self._parse_location(response, all_day)
        meeting = Meeting(
            title=self._parse_title(item),
            description=self._parse_description(item),
            classification=BOARD,
            start=start,
            end=end,
            all_day=all_day,
            time_notes=time_notes,
            location=location,
            links=self._parse_links(response),
            source=response.url,
        )

        meeting["status"] = self._get_status(meeting)
        meeting["id"] = self._get_id(meeting)

        yield meeting

    def _parse_title(self, item):
        item_str = item.css("h4.cal-header a::text").get()
        return item_str.strip() if item_str else ""

    def _parse_description(self, item):
        item_str = item.css(".cal-summary p::text").get()
        return item_str.strip() if item_str else ""

    def _parse_datetime(self, item) -> tuple[datetime, datetime, bool]:
        date_list = item.css(".month::text, .day::text, .year::text").getall()
        date_str = " ".join(date_list).strip()
        if not date_str:
            self.logger.warning(f"Missing date for item: {item.get()}")
            return None, None, False

        start_time = item.css(".mb-2 span:nth-child(2)::text").get()
        end_time = item.css(".mb-2 span:nth-child(3)::text").get()

        if start_time == "All day":
            dt = date_parser(date_str)
            return dt, dt, True

        if not start_time or not end_time:
            dt = date_parser(date_str)
            return dt, dt, False

        start_dt = date_parser(f"{date_str} {start_time.strip()}")
        end_dt = date_parser(f"{date_str} {end_time.strip()}")

        return start_dt, end_dt, False

    def _parse_location(self, response, all_day):
        item = response.css(".accordion-body ul li::text").getall()

        location = {
            "name": "",
            "address": "",
        }
        time_notes = ""

        if all_day:
            time_notes = item[2].strip() if len(item) > 2 else ""
            return location, time_notes

        if len(item) > 2:
            location["name"] = item[1].strip()
            location["address"] = item[2].strip()
        return location, time_notes

    def _parse_links(self, response):
        pdf_links = response.css("a[href*='.pdf']")
        links = [
            {
                "href": response.url,
                "title": "Meeting Details",
            }
        ]
        if pdf_links:
            links.extend(
                [
                    {
                        "href": response.urljoin(link.attrib["href"]),
                        "title": (link.css("::text").get() or "").strip()
                        or "Attachment",
                    }
                    for link in pdf_links
                ]
            )
        return links
