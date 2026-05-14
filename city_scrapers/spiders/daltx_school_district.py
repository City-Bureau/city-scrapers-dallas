from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import scrapy
from city_scrapers_core.constants import BOARD, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class DaltxSchoolDistrictSpider(CityScrapersSpider):
    name = "daltx_school_district"
    agency = "Dallas Independent School District"
    timezone = "America/Chicago"
    base_url = "https://dallasisd.community.highbond.com"
    meetings_api_url = f"{base_url}/Services/MeetingsService.svc/meetings"
    link_url = f"{base_url}/Portal/MeetingInformation.aspx"
    source_url = f"{base_url}/Portal/MeetingSchedule.aspx"
    custom_settings = {"ROBOTSTXT_OBEY": False}

    RELEVANT_TYPE_NAMES = {
        "Audit Committee Meeting Agenda and Notice",
        "Board Briefing Agenda and Notice",
        "Board Meeting Agenda and Notice",
        "Board of Trustees and Superintendent's Workshop Agenda and Notice",
        "Called Board Meeting Agenda and Notice",
        "Employee Hearing Agenda and Notice",
        "Public Hearing Agenda and Notice",
    }

    def start_requests(self):
        params = {
            "from": (date.today() - timedelta(days=365 * 3)).isoformat(),
            "to": (date.today() + timedelta(days=365)).isoformat(),
            "loadall": "true",
            "_": int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        yield scrapy.Request(
            url=f"{self.meetings_api_url}?{urlencode(params)}",
            callback=self.parse,
        )

    def parse(self, response):
        for item in response.json():
            if item.get("MeetingTypeName", "").strip() not in self.RELEVANT_TYPE_NAMES:
                continue
            yield self._create_meeting(item)

    def _create_meeting(self, item):
        meeting = Meeting(
            title=item["MeetingTypeName"].strip(),
            description="",
            classification=self._parse_classification(item["MeetingTypeName"]),
            start=datetime.strptime(item["MeetingDateTime"], "%Y-%m-%d %H:%M"),
            end=None,
            all_day=False,
            time_notes="",
            location={
                "name": item.get("MeetingLocation", ""),
                "address": "5151 Samuell Blvd., Dallas, TX 75228",
            },
            links=self._parse_links(item.get("Id")),
            source=self.source_url,
        )
        meeting["status"] = self._get_status(meeting)
        meeting["id"] = self._get_id(meeting)
        return meeting

    def _parse_classification(self, type_name):
        name_lower = type_name.lower()
        if "committee" in name_lower:
            return COMMITTEE
        if "board" in name_lower:
            return BOARD
        return NOT_CLASSIFIED

    def _parse_links(self, meeting_id):
        if not meeting_id:
            return []
        try:
            return [
                {
                    "href": f"{self.link_url}?Org=Cal&Id={int(meeting_id)}",
                    "title": "Meeting Details",
                }
            ]
        except (ValueError, TypeError):
            return []
