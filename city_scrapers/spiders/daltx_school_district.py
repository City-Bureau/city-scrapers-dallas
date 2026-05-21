import re
from datetime import date, datetime, timedelta, timezone
from html import unescape
from urllib.parse import quote, urlencode

import scrapy
from city_scrapers_core.constants import BOARD, CANCELLED, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class DaltxSchoolDistrictSpider(CityScrapersSpider):
    name = "daltx_school_district"
    agency = "Dallas Independent School District"
    timezone = "America/Chicago"
    base_url = "https://dallasisd.community.highbond.com"
    meetings_api_url = f"{base_url}/Services/MeetingsService.svc/meetings"
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

    SAMUELL_ADDRESS = "5151 Samuell Blvd., Dallas, TX 75228"
    KNOWN_LOCATIONS = {
        "Ada L. Williams Governance Room": SAMUELL_ADDRESS,
        "Theater Room": SAMUELL_ADDRESS,
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

            meeting = self._create_meeting(item)
            meeting_id = item.get("Id")

            if not meeting_id:
                meeting["status"] = self._get_status(meeting, text=item.get("Name", ""))
                meeting["id"] = self._get_id(meeting)
                yield meeting
                continue

            docs_url = (
                f"{self.meetings_api_url}/{int(meeting_id)}/meetingDocuments"
                f"?_={int(datetime.now(timezone.utc).timestamp() * 1000)}"
            )
            yield scrapy.Request(
                url=docs_url,
                callback=self.parse_meeting_documents,
                cb_kwargs={
                    "meeting": meeting,
                    "meeting_id": meeting_id,
                    "name": item.get("Name", ""),
                },
            )

    def parse_meeting_documents(self, response, meeting, meeting_id, name):
        data = response.json()
        documents = data.get("Documents", []) if isinstance(data, dict) else data

        meeting["links"] = self._parse_document_links(documents)

        if self._is_cancelled(documents, name):
            meeting["status"] = CANCELLED
        else:
            meeting["status"] = self._get_status(meeting, text=name)

        video_url = (
            f"{self.meetings_api_url}/{int(meeting_id)}/meetingData"
            f"?_={int(datetime.now(timezone.utc).timestamp() * 1000)}"
        )
        yield scrapy.Request(
            url=video_url,
            callback=self.parse_video_link,
            cb_kwargs={"meeting": meeting},
        )

    def parse_video_link(self, response, meeting):
        data = response.json()
        video_href = data.get("MeetingExternalLinkUrl", "")
        if video_href:
            meeting["links"].append({"href": video_href, "title": "Video"})
        meeting["id"] = self._get_id(meeting)
        yield meeting

    def _create_meeting(self, item):
        title = item.get("MeetingTypeName", "").strip()
        raw_dt = item.get("MeetingDateTime", "")
        try:
            start = datetime.strptime(raw_dt, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            self.logger.warning("Could not parse MeetingDateTime: %r", raw_dt)
            start = None
        return Meeting(
            title=title,
            description="",
            classification=self._parse_classification(title),
            start=start,
            end=None,
            all_day=False,
            time_notes=self._parse_time_notes(start),
            location=self._parse_location(item),
            links=[],
            source=self.source_url,
        )

    def _parse_classification(self, type_name):
        name_lower = type_name.lower()
        if "committee" in name_lower:
            return COMMITTEE
        if "board" in name_lower or "hearing" in name_lower:
            return BOARD
        return NOT_CLASSIFIED

    def _parse_location(self, item):
        location = item.get("MeetingLocation", "").strip()
        if not location:
            return {"name": "", "address": ""}

        if location in self.KNOWN_LOCATIONS:
            return {"name": location, "address": self.KNOWN_LOCATIONS[location]}

        # Split "Building Name 1234 Street City, ST ZIP" into name and address
        match = re.search(r"\s+(\d{3,5}\s+[A-Z])", location)
        if match:
            name = location[: match.start()].strip().rstrip(".")
            address = location[match.start() :].strip()
            return {"name": name, "address": address}

        return {"name": location, "address": ""}

    def _parse_time_notes(self, start):
        if start is None or (start.hour == 0 and start.minute == 0):
            return "See source website for meeting time"
        return ""

    def _is_cancelled(self, documents, name=""):
        if "cancelled" in name.lower() or "canceled" in name.lower():
            return True
        for doc in documents:
            if not doc.get("IsPublic"):
                continue
            text = f"{doc.get('AgendaCover', '')} {doc.get('Name', '')}".lower()
            if "cancelled" in text or "canceled" in text:
                return True
        return False

    def _parse_document_links(self, documents):
        links = []
        seen = set()
        for doc in documents:
            if not doc.get("IsPublic"):
                continue
            href = self._build_document_url(doc)
            if not href or href in seen:
                continue
            seen.add(href)
            doc_type = doc.get("DocumentType")
            if doc_type in (1, 4):
                title = "Agenda"
            elif doc_type in (2, 10):
                title = "Minutes"
            else:
                title = "Document"
            links.append({"href": href, "title": title})
        return links

    def _build_document_url(self, doc):
        doc_id = doc.get("Id")
        name = (doc.get("Name") or "").strip()
        if not doc_id:
            return None
        if name:
            encoded_name = quote(unescape(name), safe="")
            return f"{self.base_url}/document/{doc_id}/{encoded_name}.pdf"
        return f"{self.base_url}/document/{doc_id}/"
