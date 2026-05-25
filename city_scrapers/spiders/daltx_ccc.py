import json
from datetime import date, datetime, timezone
from html import unescape
from urllib.parse import quote, urlencode

import scrapy
from city_scrapers_core.constants import (
    BOARD,
    CANCELLED,
    CITY_COUNCIL,
    COMMISSION,
    COMMITTEE,
    NOT_CLASSIFIED,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.relativedelta import relativedelta


class DaltxCccSpider(CityScrapersSpider):
    name = "daltx_ccc"
    agency = "Dallas County Commissioners Court"
    timezone = "America/Chicago"
    source_url = "https://dallascounty.civicweb.net/Portal/MeetingSchedule.aspx"
    meetings_api_url = (
        "https://dallascounty.civicweb.net/Services/MeetingsService.svc/meetings"
    )
    video_api_url = "https://dallascounty.civicweb.net/api/videolink"
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }
    include_non_public_documents = True
    AGENDA_TYPES = {1, 4}
    MINUTES_TYPES = {2, 10}
    KNOWN_LOCATIONS = [
        {
            "keywords": [
                "commissioners court room",
                "george allen",
                "records building",
            ],
            "address": "500 Elm Street, Dallas, TX 75202",
        },
        {
            "keywords": ["allen clemson courtroom"],
            "address": "411 Elm Street, Dallas, TX 75202",
        },
    ]
    commissioners_court_description = (
        "The Dallas County Commissioners Court meets twice a month on the first and "
        "third Tuesday, at 9:00 AM in the Commissioners Courtroom in the Dallas County "
        "Records Building, except for July when the Court meets only on the first Tuesday."  # noqa
    )

    def _get_cache_busting_timestamp(self):
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    def start_requests(self):
        today = date.today()
        from_date = (today - relativedelta(years=7)).isoformat()
        to_date = (today + relativedelta(years=1)).isoformat()

        params = {
            "from": from_date,
            "to": to_date,
            "_": self._get_cache_busting_timestamp(),
        }

        url = f"{self.meetings_api_url}?{urlencode(params)}"
        yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response):
        for item in response.json():
            title = self._parse_title(item)
            start = self._parse_start(item)

            meeting = Meeting(
                title=title,
                description=(
                    self.commissioners_court_description
                    if title == "Commissioners Court"
                    else ""
                ),  # noqa
                classification=self._parse_classification(title),
                start=start,
                end=None,
                all_day=False,
                time_notes=self._parse_time_notes(start),
                location=self._parse_location(item),
                links=[],
                source=self.source_url,
            )

            meeting_id = item.get("Id")
            if not meeting_id:
                meeting["status"] = self._get_status(meeting)
                meeting["id"] = self._get_id(meeting)
                yield meeting
                continue

            docs_url = (
                f"{self.meetings_api_url}/{meeting_id}/meetingDocuments"
                f"?_={self._get_cache_busting_timestamp()}"
            )

            yield scrapy.Request(
                url=docs_url,
                callback=self.parse_meeting_documents,
                cb_kwargs={"meeting": meeting, "meeting_id": meeting_id},
            )

    def parse_meeting_documents(self, response, meeting, meeting_id):
        documents = response.json()

        meeting["links"].extend(self._parse_document_links(documents))
        meeting["links"] = self._dedupe_links(meeting["links"])

        if self._is_cancelled(documents):
            meeting["status"] = CANCELLED
        else:
            meeting["status"] = self._get_status(meeting)

        video_url = (
            f"{self.video_api_url}/{meeting_id}"
            f"?_={self._get_cache_busting_timestamp()}"
        )

        yield scrapy.Request(
            url=video_url,
            callback=self.parse_video_link,
            cb_kwargs={"meeting": meeting, "meeting_id": meeting_id},
        )

    def parse_video_link(self, response, meeting, meeting_id):
        video_href = self._parse_video_link(response)

        if video_href:
            meeting["links"].append({"href": video_href, "title": "Video"})

        meeting["links"] = self._dedupe_links(meeting["links"])

        meeting_data_url = (
            f"{self.meetings_api_url}/{meeting_id}/meetingData"
            f"?_={self._get_cache_busting_timestamp()}"
        )

        yield scrapy.Request(
            url=meeting_data_url,
            callback=self.parse_meeting_data,
            cb_kwargs={"meeting": meeting},
        )

    def parse_meeting_data(self, response, meeting):
        data = response.json()

        ext_url = (data.get("MeetingExternalLinkUrl") or "").strip()
        ext_name = (data.get("MeetingExternalLinkName") or "").strip()
        if ext_url:
            meeting["links"].append({"href": ext_url, "title": ext_name or "Document"})

        ext_minutes_url = (data.get("MeetingExternalMinutesLinkUrl") or "").strip()
        ext_minutes_name = (data.get("MeetingExternalMinutesLinkName") or "").strip()
        if ext_minutes_url:
            meeting["links"].append(
                {"href": ext_minutes_url, "title": ext_minutes_name or "Document"}
            )

        meeting["links"] = self._dedupe_links(meeting["links"])
        meeting["id"] = self._get_id(meeting)
        yield meeting

    def _parse_video_link(self, response):
        text = response.text.strip()

        if not text or text == '""':
            return None

        if text.startswith("http"):
            return text

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            self.logger.warning("Failed to decode JSON response from video API")
            return None

        if isinstance(data, str):
            data = data.strip()
            if not data:
                return None
            if data.startswith("http"):
                return data
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                self.logger.warning(
                    "Failed to decode double-encoded JSON response from video API"
                )
                return None

        if isinstance(data, list):
            if not data:
                return None
            data = data[0]

        if not isinstance(data, dict) or not data.get("ShowVideoLink"):
            return None

        youtube_event_id = data.get("YouTubeEventId")
        if data.get("YouTube") and youtube_event_id:
            return f"https://www.youtube.com/watch?v={youtube_event_id}"

        document_id = data.get("DocumentId") or data.get("Id")
        if document_id:
            return (
                f"https://dallascounty.civicweb.net/document/"
                f"{document_id}/?splitscreen=true&media=true"
            )

        return None

    def _is_cancelled(self, documents):
        for doc in documents:
            if not doc.get("IsPublic") and not self.include_non_public_documents:
                continue

            name = (doc.get("Name") or "").lower()
            agenda_cover = (doc.get("AgendaCover") or "").lower()
            if any(
                kw in name or kw in agenda_cover for kw in ["cancelled", "canceled"]
            ):
                return True
            html = (doc.get("Html") or "").lower()
            if "cancelled" in html or "canceled" in html:
                return True

        return False

    def _parse_document_links(self, documents):
        minutes_pdf_names = {
            unescape((doc.get("Name") or "").strip())
            for doc in documents
            if doc.get("DocumentType") in self.MINUTES_TYPES
            and not doc.get("Html")
            and (doc.get("IsPublic") or self.include_non_public_documents)
        }

        agenda_by_name = {}
        other_links = []

        for doc in documents:
            if not doc.get("IsPublic") and not self.include_non_public_documents:
                continue

            href = self._build_document_url(doc)
            if not href:
                continue

            name = unescape((doc.get("Name") or "").strip())
            doc_type = doc.get("DocumentType")

            if doc_type in self.AGENDA_TYPES:
                label = "Agenda" if doc.get("Html") else "Agenda Packet"
            elif doc_type in self.MINUTES_TYPES:
                label = "Minutes" if doc.get("Html") else "Minutes Packet"
            elif doc.get("Html") and name in minutes_pdf_names:
                label = "Minutes"
            else:
                label = "Document"

            link = {"href": href, "title": label}

            if label == "Agenda":
                if name not in agenda_by_name:
                    agenda_by_name[name] = link
            else:
                other_links.append(link)

        return list(agenda_by_name.values()) + other_links

    def _build_document_url(self, doc):
        doc_id = doc.get("Id")
        name = (doc.get("Name") or "").strip()

        if not doc_id:
            return None

        if doc.get("Html"):
            return f"https://dallascounty.civicweb.net/document/{doc_id}/?printPdf=true"

        if name:
            encoded_name = quote(unescape(name), safe="")
            return (
                f"https://dallascounty.civicweb.net/document/"
                f"{doc_id}/{encoded_name}.pdf"
            )

        return f"https://dallascounty.civicweb.net/document/{doc_id}/"

    def _dedupe_links(self, links):
        seen = set()
        unique_links = []

        for link in links:
            key = (link.get("href", ""), link.get("title", ""))
            if key in seen:
                continue
            seen.add(key)
            unique_links.append(link)

        return unique_links

    def _parse_title(self, item):
        title = item.get("Name", "")
        title = title.replace("- ", " - ")
        parts = title.rsplit(" - ", 1)
        title = parts[0] if len(parts) > 1 else title
        return title.replace("  ", " ").strip()

    def _parse_classification(self, title):
        if "City Council" in title:
            return CITY_COUNCIL
        if "Committee" in title:
            return COMMITTEE
        if "Court" in title or "Board" in title:
            return BOARD
        if "Commission" in title:
            return COMMISSION
        return NOT_CLASSIFIED

    def _parse_start(self, item):
        dt_str = item.get("MeetingDateTime", "")
        if dt_str:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        return None

    def _parse_time_notes(self, start):
        if start and start.hour == 0 and start.minute == 0:
            return "Please check meeting source website or attachment for more accurate meeting start time"  # noqa
        return ""

    def _parse_location(self, item):
        location = item.get("MeetingLocation", "").strip()
        location_lower = location.lower()

        if "dallas, texas" in location_lower:
            return {"name": "", "address": location}

        for entry in self.KNOWN_LOCATIONS:
            if any(kw in location_lower for kw in entry["keywords"]):
                return {"name": location, "address": entry["address"]}

        return {"name": location, "address": ""}
