from collections import defaultdict

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
                description="",
                classification=CITY_COUNCIL,
                start=self.legistar_start(event),
                end=None,
                all_day=False,
                time_notes="",
                location=self._parse_location(event),
                links=self.legistar_links(event),
                source=self.legistar_source(event),
            )

            meeting["status"] = self._get_status(
                meeting, text=meeting["location"]["name"] or ""
            )
            meeting["id"] = self._get_id(meeting)

            yield meeting

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

    def _parse_legistar_events(self, response):
        """Override the parent method to fix iCalendar URL issue"""
        events_table = response.css("table.rgMasterTable")[0]

        headers = []
        for header in events_table.css("th[class^='rgHeader']"):
            header_text = (
                " ".join(header.css("*::text").extract()).replace("&nbsp;", " ").strip()
            )
            header_inputs = header.css("input")
            if header_text:
                headers.append(header_text)
            elif len(header_inputs) > 0:
                headers.append(header_inputs[0].attrib["value"])
            else:
                headers.append(header.css("img")[0].attrib["alt"])

        events = []
        for row in events_table.css("tr.rgRow, tr.rgAltRow"):
            try:
                data = defaultdict(lambda: None)

                for header, field in zip(headers, row.css("td")):
                    field_text = (
                        " ".join(field.css("*::text").extract())
                        .replace("&nbsp;", " ")
                        .strip()
                    )
                    url = None
                    if len(field.css("a")) > 0:
                        link_el = field.css("a")[0]
                        if "onclick" in link_el.attrib and link_el.attrib[
                            "onclick"
                        ].startswith(("radopen('", "window.open", "OpenTelerikWindow")):
                            url = response.urljoin(
                                link_el.attrib["onclick"].split("'")[1]
                            )
                        elif "href" in link_el.attrib:
                            url = response.urljoin(link_el.attrib["href"])

                    if url and ("View.ashx?M=IC" in url):
                        data["iCalendar"] = {"url": url}
                    elif url:
                        value = {"label": field_text, "url": url}
                        data[header] = value
                    else:
                        data[header] = field_text

                ical_url = (
                    data["iCalendar"].get("url")
                    if isinstance(data.get("iCalendar"), dict)
                    else None
                )
                if ical_url is not None:
                    if ical_url in self._scraped_urls:
                        continue
                    self._scraped_urls.add(ical_url)
                if data:
                    events.append(dict(data))
            except Exception as e:
                self.logger.warning(f"Error processing row: {e}", exc_info=True)

        return events
