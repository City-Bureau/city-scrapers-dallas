from city_scrapers_core.constants import CITY_COUNCIL
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import LegistarSpider


class DaltxCityCouncilSpider(LegistarSpider):
    name = "daltx_city_council"
    agency = "Dallas City Council"
    timezone = "America/Chicago"
    start_urls = ["https://cityofdallas.legistar.com/Calendar.aspx"]
    # Add the titles of any links not included in the scraped results
    link_types = []

    DEFAULT_MEETING_TIME = "0:00 AM"

    def _preprocess_meeting_time(self, event):
        """Preprocess meeting time to ensure it has a valid value."""
        return event.get("Meeting Time") or self.DEFAULT_MEETING_TIME

    def parse_legistar(self, events):
        """
        `parse_legistar` should always `yield` Meeting items.

        Change the `_parse_title`, `_parse_start`, etc methods to fit your scraping
        needs.
        """
        for event in events:
            event["Meeting Time"] = self._preprocess_meeting_time(event)
            meeting = Meeting(
                title=event["Name"],
                description=self._parse_description(event),
                classification=self._parse_classification(event),
                start=self.legistar_start(event),
                end=self._parse_end(event),
                all_day=self._parse_all_day(event),
                time_notes=self._parse_time_notes(event),
                location=self._parse_location(event),
                links=self.legistar_links(event),
                source=self.legistar_source(event),
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_description(self, item):
        """Parse or generate meeting description."""
        return ""

    def _parse_classification(self, item):
        """Parse or generate classification from allowed options."""
        return CITY_COUNCIL

    def _parse_end(self, item):
        """Parse end datetime as a naive datetime object. Added by pipeline if None"""
        return None

    def _parse_time_notes(self, item):
        """Parse any additional notes on the timing of the meeting"""
        return ""

    def _parse_all_day(self, item):
        """Parse or generate all-day status. Defaults to False."""
        return False

    def _parse_location(self, item):
        """Parse or generate location."""
        address = "1500 Marilla Street Dallas, TX 75201"
        location = item.get("Meeting Location", "")
        if isinstance(location, dict):
            address = location.get("url", "")
            location = location.get("label", "")
        return {
            "name": location,
            "address": address,
        }
