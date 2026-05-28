import json
import re
from datetime import datetime
from itertools import groupby
from urllib.parse import urljoin

import scrapy
from city_scrapers_core.constants import BOARD, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class DaltxDartSpider(CityScrapersSpider):
    name = "daltx_dart"
    agency = "Dallas Area Rapid Transit (DART)"
    timezone = "America/Chicago"

    # Current meetings + upcoming calendar
    start_urls = "https://www.dart.org/about/public-access-information/board-meetings-information"  # noqa

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    # Archive base URL — pages are numbered -page-1-, -page-2-, ...
    ARCHIVE_URL = (
        "https://www.dart.org/about/public-access-information/"
        "board-meetings-information/board-meetings-agenda-and-minutes-archive/"
    )

    # Video archive — three paginated tabs
    VIDEO_BASE_URL = "https://dart.new.swagit.com"
    VIDEO_TABS = [
        "/views/561/board-of-directors-archive",
        "/views/561/committees-archive",
        "/views/561/treac-archive",
    ]

    # Default meeting time — falls back to midnight (00:00) when no time is available.
    DEFAULT_MEETING_TIME = {"hour": 0, "minute": 0}

    END_DATE = datetime(datetime.now().year - 3, 1, 1)

    LOCATION = {
        "name": "DART Headquarters, Board Room",
        "address": "1401 Pacific Ave, Dallas, TX 75202",
    }

    DESCRIPTION = ""

    TRINITY_TITLE_ALIASES = {
        "treac": "trinity railway express advisory committee",
        "tre advisory committee": "trinity railway express advisory committee",
        "trinity railway advisory committee": "trinity railway express advisory committee",  # noqa
        "trinity railway": "trinity railway express advisory committee",
    }

    # Populated while video pages are scraped.
    # Keyed by datetime.date → list of {"title": str, "href": str}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._video_index = {}

    def start_requests(self):
        # Upcoming meetings DART page
        yield scrapy.Request(self.start_urls, callback=self.parse)

        # Video archive tabs (run in parallel with the main crawl)
        for tab in self.VIDEO_TABS:
            yield scrapy.Request(
                self.VIDEO_BASE_URL + tab,
                callback=self._parse_video_page,
            )

    def parse(self, response):
        """
        Main page contains two JS arrays:
          1. `var data`     — current meeting records (one row per agenda item)
          2. `var gridData` — upcoming calendar events (one row per event)

        After parsing the main page, kick off archive pagination.
        Dates already present in `var data` are excluded from `var gridData`
        to avoid duplicate meetings.
        """
        self.DESCRIPTION = (
            response.css("div.mr-3 p:first-of-type::text").get("").strip()
        )
        rows = self._extract_js_array(response.text, "var data")
        yield from self._yield_meetings_from_rows(rows, response.url)

        seen_dates = {
            dt.date()
            for r in rows
            if (dt := self._parse_dt(r.get("meetingDate"), None))
        }
        yield from self._parse_grid_data(response, exclude_dates=seen_dates)
        yield from self._paginate_archive(page=1)

    def parse_archive(self, response):
        """Parse an archive page and follow to the next if rows were found and
        any are within the cutoff window (archives are newest-first)."""
        rows = self._extract_js_array(response.text, "var data")
        if not rows:
            return  # No more pages — stop pagination

        dates = [self._parse_dt(r.get("meetingDate"), None) for r in rows]
        dates = [d for d in dates if d is not None]
        has_recent_dates = any(d >= self.END_DATE for d in dates)

        yield from self._yield_meetings_from_rows(rows, response.url)

        if has_recent_dates:
            next_page = response.meta["page"] + 1
            yield from self._paginate_archive(next_page)

    def _paginate_archive(self, page: int):
        """Yield a Scrapy Request for an archive page."""
        url = f"{self.ARCHIVE_URL}-page-{page}-"
        yield scrapy.Request(
            url,
            callback=self.parse_archive,
            meta={"page": page},
        )

    #  Video pages
    def _parse_video_page(self, response):
        """
        Parse one Video archive tab page and populate _video_index.
        Follows pagination via <a rel='next'> links.
        Pages are newest-first; stops early once rows fall before END_DATE.
        """
        rows = response.css("table.videos tbody tr")
        if not rows:
            self.logger.warning("Video page: no rows found")
            return

        for row in rows:
            link = row.css("td:first-child a")
            title = link.css("::text").get("").strip()
            href = link.attrib.get("href", "")
            date_text = row.css("td:nth-child(2)::text").get("").strip()

            try:
                dt = datetime.strptime(date_text, "%b %d, %Y").date()
            except ValueError:
                self.logger.warning("Video page: could not parse date %r", date_text)
                continue

            if datetime(dt.year, dt.month, dt.day) < self.END_DATE:
                return  # Newest-first — everything after this is older; stop

            full_href = urljoin(self.VIDEO_BASE_URL, href)
            self._video_index.setdefault(dt, []).append(
                {"title": title, "href": full_href}
            )

        next_href = response.css("a[rel='next']::attr(href)").get()
        if next_href:
            yield response.follow(next_href, callback=self._parse_video_page)

    def _titles_match(self, meeting_title: str, video_title: str) -> bool:
        """
        Return True if the meeting title contains at least 50% of the
        words from the video title (after normalization).
        Video titles are shorter and more canonical.
        """
        meeting_words = set(self._norm_title(meeting_title).split())
        video_words = set(self._norm_title(video_title).split())
        if not video_words:
            return False
        overlap = meeting_words & video_words
        return len(overlap) / len(video_words) >= 0.5

    def _find_video_link(self, meeting_start: datetime, title: str) -> dict | None:
        candidates = self._video_index.get(meeting_start.date(), [])
        if not candidates:
            self.logger.warning("No video candidates for %s", meeting_start)
            return None

        matches = [c for c in candidates if self._titles_match(title, c["title"])]
        if not matches:
            self.logger.warning("No video matches for %s", title)
            return None

        # If multiple match, prefer the one with the most word overlap
        best_match = max(
            matches,
            key=lambda c: len(
                set(self._norm_title(title).split())
                & set(self._norm_title(c["title"]).split())
            ),
        )
        return {"href": best_match["href"], "title": "Video"}

    def _norm_title(self, title: str) -> str:
        normalized = title.lower()
        normalized = normalized.replace("-", " ")
        normalized = re.sub(r"\(.*?\)", "", normalized)  # strip (Work Session)
        normalized = re.sub(r"[^a-z0-9 ]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        for alias, expansion in self.TRINITY_TITLE_ALIASES.items():
            normalized = normalized.replace(alias, expansion)
        return normalized

    def _parse_grid_data(self, response, exclude_dates=None):
        """
        `var gridData` rows are one-per-event with just title + date.
        Each row becomes its own Meeting directly.
        Skips any date already present in `var data` (passed via exclude_dates).
        """
        exclude_dates = exclude_dates or set()
        for item in self._extract_js_array(response.text, "var gridData"):
            dt = self._parse_dt(item.get("eventDate"), None)
            if not dt or dt < self.END_DATE:
                continue
            if dt.date() in exclude_dates:
                continue

            links = []
            video = self._find_video_link(dt, item.get("title", ""))
            if video:
                links.append(video)

            meeting = self._build_meeting(
                item,
                date_field="eventDate",
                time_field=None,
                links=links,
                url=response.url,
            )
            if meeting:
                yield meeting

    def _yield_meetings_from_rows(self, rows: list, url: str):
        """
        Group `var data` rows by (meetingDate, sortOrder) — which uniquely
        identifies one meeting — then yield one Meeting per group, collecting
        all meetingItemDocument links as agenda item attachments.
        """
        rows = [
            r
            for r in rows
            if (self._parse_dt(r.get("meetingDate"), None) or datetime.min)
            >= self.END_DATE
        ]
        rows.sort(key=lambda r: (r.get("meetingDate", ""), r.get("sortOrder", 0)))

        for _, group in groupby(
            rows, key=lambda r: (r.get("meetingDate", ""), r.get("sortOrder", 0))
        ):
            group = list(group)
            rep = group[0]

            # Base links: agenda packet + supplemental documents
            links = self._parse_links(rep)

            # Per-agenda-item document links
            for row in group:
                doc = row.get("meetingItemDocument")
                if doc and doc.get("url"):
                    links.append(
                        {
                            "href": doc["url"],
                            "title": row.get("meetingItemTitle")
                            or doc.get("title", "Agenda Item"),
                        }
                    )

            # Attach video if one matches this meeting
            start = self._parse_dt(rep.get("meetingDate"), rep.get("meetingTime"))
            if start:
                video = self._find_video_link(start, rep.get("title", ""))
                if video:
                    links.append(video)

            meeting = self._build_meeting(
                rep,
                date_field="meetingDate",
                time_field="meetingTime",
                links=links,
                url=url,
            )
            if meeting:
                yield meeting

    def _build_meeting(self, item, date_field, time_field, links, url):
        """Construct, stamp, and return a Meeting item, or None if date is missing."""  # noqa
        start = self._parse_dt(
            item.get(date_field),
            item.get(time_field) if time_field else None,
        )
        if start is None:
            self.logger.warning("No date found for '%s'", item.get("title", ""))
            return None

        meeting = Meeting(
            title=self._parse_title(item),
            description=self.DESCRIPTION,
            classification=self._parse_classification(item),
            start=start,
            end=None,
            all_day=False,
            time_notes="",
            location=self.LOCATION,
            links=links,
            source=url,
        )
        meeting["status"] = self._get_status(meeting)
        meeting["id"] = self._get_id(meeting)
        return meeting

    def _extract_js_array(self, text: str, var_name: str) -> list:
        """Extract and parse a JS array assigned to `var_name` in page source."""
        pattern = re.escape(var_name) + r"\s*=\s*(\[.*\]);"
        match = re.search(pattern, text)
        if not match:
            self.logger.warning("Could not find '%s' in page source", var_name)
            return []
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            self.logger.error("JSON parse error for '%s': %s", var_name, e)
            return []

    def _parse_title(self, item: dict) -> str:
        """Parse meeting title, stripping leading date prefixes like '2026-05-18 '."""
        title = item.get("title", "").strip()
        title = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", title)
        title = re.sub(r"\((Cancell?ed?)\)", r"\1", title, flags=re.IGNORECASE)
        return title.strip()

    def _parse_classification(self, item: dict) -> int:
        """Return BOARD for board meetings, COMMITTEE for committee meetings."""
        title = item.get("title", "").lower()
        if "board" in title:
            return BOARD
        if "committee" in title:
            return COMMITTEE
        return NOT_CLASSIFIED

    def _parse_dt(self, date_str: str | None, time_str: str | None) -> datetime | None:
        """
        Parse a naive datetime from an ISO date string and an optional time
        string like '1:00 p.m.' or '6:00 p.m.'.
        Falls back to DEFAULT_MEETING_TIME when time is absent or unparseable.
        """
        if not date_str:
            self.logger.warning("Missing date string")
            return None
        try:
            dt = datetime.fromisoformat(date_str[:10])
        except ValueError:
            self.logger.warning("Could not parse date: %s", date_str)
            return None

        hour, minute = self._parse_time_str(time_str)
        return dt.replace(hour=hour, minute=minute)

    def _parse_time_str(self, time_str: str | None) -> tuple[int, int]:
        """
        Parse '1:00 p.m.' / '6:00 p.m.' style strings into (hour, minute).
        Returns DEFAULT_MEETING_TIME if the string is absent or unparseable.
        """
        if not time_str:
            return (
                self.DEFAULT_MEETING_TIME["hour"],
                self.DEFAULT_MEETING_TIME["minute"],
            )

        normalised = (
            time_str.strip()
            .upper()
            .replace(".", "")
            .replace("A M", "AM")
            .replace("P M", "PM")
        )
        for fmt in ("%I:%M %p", "%I %p"):
            try:
                t = datetime.strptime(normalised, fmt)
                return t.hour, t.minute
            except ValueError:
                self.logger.warning(
                    "Time string '%s' does not match format '%s'", normalised, fmt
                )
                continue

        self.logger.warning("Could not parse time string: '%s'", time_str)
        return self.DEFAULT_MEETING_TIME["hour"], self.DEFAULT_MEETING_TIME["minute"]

    def _parse_links(self, item: dict) -> list[dict]:
        """Collect agenda packet and supplemental document links."""
        doc_keys = ["agendaDocument", "supplementalInformationDocument", "agendaPacket"]
        return [
            {
                "href": item[key]["url"],
                "title": item[key].get("title", key),
            }
            for key in doc_keys
            if item.get(key) and item[key].get("url")
        ]
