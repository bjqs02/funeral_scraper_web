"""Funeral + coffin-room scraper core (台中市生命禮儀管理處 - 崇德館).

Re-usable library: fetch + parse + merge. No xlsx, no CLI, no dedup state.
Consumed by scrape_to_json.py to produce docs/data/latest.json for the
GitHub Pages frontend.

Mirror of publicStuff/funeral_scraper/scraper.py (lines 28-399); kept as a
separate self-contained file so the funeral_scraper_purejs/ folder can be
moved to its own repo without dragging the xlsx-based sibling.
"""

from __future__ import annotations

import gzip
import json
import re
import ssl
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from html import unescape
from http.cookiejar import CookieJar
from urllib import request as urlrequest
from urllib.parse import urlencode

FAREWELL_URL = "https://mortuary.taichung.gov.tw/Frontend/Farewell.aspx"
COFFIN_URL = "https://mortuary.taichung.gov.tw/frontend/CoffinUse.aspx"

UNIT_CODE_CHONGDE = "2"
UNIT_NAME_CHONGDE = "崇德館"

HIGHLIGHT_RESIDENCE_KEYWORDS = ["北區"]


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

REQUEST_TIMEOUT_SEC = 30
SLEEP_BETWEEN_REQUESTS_SEC = 1.5

REQUEST_MAX_ATTEMPTS = 3
REQUEST_RETRY_BACKOFF_SEC = 3.0

# Colour codes used by CoffinUse.aspx to distinguish gender.
# Verified empirically by cross-matching 11/11 names from Farewell page
# (gender column) against the same names appearing on CoffinUse page.
COFFIN_COLOUR_MALE = "0867a1"
COFFIN_COLOUR_FEMALE = "cc0602"


@dataclass
class FarewellRecord:
    name: str
    gender: str
    age: str
    residence: str
    hall: str
    farewell_date: str
    time_range: str
    public_ceremony: str
    unit: str
    source_url: str
    scraped_at: str
    highlight_residence: bool
    visit_start_date: str = ""
    visit_end_date: str = ""
    visit_location: str = ""
    visit_note: str = ""
    is_new: bool = False

    def dedup_key(self) -> str:
        return "|".join([
            self.unit,
            self.name,
            self.farewell_date,
            self.time_range,
            self.hall,
        ])


@dataclass
class CoffinDayRoom:
    """One record per (day, room, person). The CoffinUse page stacks multiple
    people inside a single matrix cell when more than one coffin shares a
    room on the same day, so a physical cell may unfold into multiple rows
    of this dataclass. ``name == "不公開"`` means the family opted out of
    public disclosure; such rows are kept but excluded from name-based
    joins with the farewell list."""
    occupancy_date: str
    room_number: str
    name: str
    age: str
    gender: str
    residence: str
    mortician: str
    unit: str


_TAG_RE = re.compile(r"<[^>]+>")


def _build_opener() -> urlrequest.OpenerDirector:
    # SSL verification disabled: some Micron internal environments ship an
    # incomplete CA chain that breaks verification against public gov sites.
    # Acceptable here because the target is a public government docs and the
    # data is non-sensitive; do NOT copy this pattern for sensitive endpoints.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urlrequest.build_opener(
        urlrequest.HTTPSHandler(context=ctx),
        urlrequest.HTTPCookieProcessor(CookieJar()),
    )


def _read(resp) -> str:
    raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def _get_form_tokens(html_text: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for key in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        m = re.search(rf'id="{key}"[^>]*value="([^"]*)"', html_text)
        if not m:
            raise RuntimeError(f"找不到 ASP.NET 表單欄位: {key}")
        tokens[key] = m.group(1)
    return tokens
def _open_with_retry(opener: urlrequest.OpenerDirector, req:urlrequest.Request) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, REQUEST_MAX_ATTEMPTS + 1):
        try:
            with opener.open(req, timeout =REQUEST_TIMEOUT_SEC) as resp:
                return_read(resp) 
        except Exception as exc:
            last_exc = exc
            if attempt < REQUEST_MAX_ATTEMPTS:
                time.sleep(REQUEST_RETRY_BACKOFF_SEC * attempt)
    raise last_exc

def _post_form(url: str, fields: dict[str, str]) -> str:
    """GET url to pick up ViewState + session cookie, then POST `fields` plus
    those tokens to the same url. Returns the response body HTML."""
    opener = _build_opener()
    headers_get = {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip",
        "Accept": "text/html,application/xhtml+xml",
    }
    page = _open_with_retry(
        opener, urlrequest.Request(url, headers=headers_get))
    tokens = _get_form_tokens(page)

    body = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        **tokens,
        **fields,
    }
    headers_post = {
        **headers_get,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": url,
        "Origin": "https://mortuary.taichung.gov.tw",
    }
    return _open_with_retry(
        opener,
        urlrequest.Request(
            url,
            data=urlencode(body).encode("utf-8"),
            method="POST",
            headers=headers_post,
        ),
    )
    
def _strip_tags(s: str) -> str:
    text = _TAG_RE.sub("", s)
    return " ".join(unescape(text).split()).strip()


def _roc_date(d: date) -> str:
    return f"{d.year - 1911:03d}/{d.month:02d}/{d.day:02d}"


def fetch_farewell_day(unit_code: str, target_day: date) -> str:
    search_option_by_date = "1"
    return _post_form(FAREWELL_URL, {
        "ctl00$CphContent$ddl_Unit": unit_code,
        "ctl00$CphContent$ddl_SearchOption": search_option_by_date,
        "ctl00$CphContent$tb_SDay": _roc_date(target_day),
        "ctl00$CphContent$btn_send": "查詢",
    })


def fetch_coffin_day(unit_code: str, target_day: date) -> str:
    return _post_form(COFFIN_URL, {
        "ctl00$CphContent$ddl_Unit": unit_code,
        "ctl00$CphContent$tb_SDay": _roc_date(target_day),
        "ctl00$CphContent$btn_send": "查詢",
    })


_FAREWELL_BLOCK_RE = re.compile(
    r'<span id="CphContent_lb_Farewell">(.*?)</span>',
    re.DOTALL,
)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TH_RE = re.compile(r"<th[^>]*>(.*?)</th>", re.DOTALL)


def parse_farewell(
    page_html: str,
    *,
    unit_name: str,
    source_url: str,
    scraped_at: str,
) -> list[FarewellRecord]:
    block_m = _FAREWELL_BLOCK_RE.search(page_html)
    if not block_m:
        return []
    block = block_m.group(1)

    expected_columns = 9
    records: list[FarewellRecord] = []
    for row_m in _ROW_RE.finditer(block):
        cells = [_strip_tags(c) for c in _TD_RE.findall(row_m.group(1))]
        # Header row uses <th>, not <td>, so _TD_RE finds nothing and we skip.
        if len(cells) < expected_columns:
            continue
        # Column order from the rendered table:
        # 項次 / 姓名 / 性別 / 年齡 / 戶籍地 / 禮廳 / 日期 / 時間 / 公祭時間
        _, name, gender, age, residence, hall, fdate, ftime, public = cells[:expected_columns]
        residence_hit = any(k in residence for k in HIGHLIGHT_RESIDENCE_KEYWORDS)
        records.append(FarewellRecord(
            name=name,
            gender=gender,
            age=age,
            residence=residence,
            hall=hall,
            farewell_date=fdate,
            time_range=ftime,
            public_ceremony=public,
            unit=unit_name,
            source_url=source_url,
            scraped_at=scraped_at,
            highlight_residence=residence_hit,
        ))
    return records


# CoffinUse renders a matrix: rows = dates, columns = stop-coffin rooms 01..22.
# Each cell contains zero or more <div class='KeepNoWrap'> entries, one per
# person stored in that room on that day. Each entry has the shape:
#   <span style='color:#XXXXXX;'>NAME</span>[AGE]<br/>RESIDENCE<br/>MORTICIAN
# Page header line "5/24<br>(日)" gives the date (MM/DD only, year inferred
# from the query date span).
_COFFIN_PERSON_RE = re.compile(
    r"<div class='KeepNoWrap'>"
    r"<span style='color:#([0-9A-Fa-f]+);'>([^<]+)</span>"
    r"(?:\[([^\]]*)\])?"
    r"<br/>([^<]*)<br/>([^<]*)"
    r"</div>",
    re.DOTALL,
)
_COFFIN_DATE_TH_RE = re.compile(
    r"<th class='headcol'[^>]*>(\d{1,2})/(\d{1,2})<br>",
)


def _coffin_gender(colour_hex: str) -> str:
    c = colour_hex.lower()
    if c == COFFIN_COLOUR_MALE:
        return "男"
    if c == COFFIN_COLOUR_FEMALE:
        return "女"
    return ""


def parse_coffin(
    page_html: str,
    *,
    unit_name: str,
    query_year: int,
) -> list[CoffinDayRoom]:
    # Find the result table region. The page has only one table with the
    # 22-room header, so we anchor on the first column header "01號".
    anchor = page_html.find(">01號<")
    if anchor < 0:
        return []
    tbl_start = page_html.rfind("<table", 0, anchor)
    tbl_end = page_html.find("</table>", anchor)
    if tbl_start < 0 or tbl_end < 0:
        return []
    table_html = page_html[tbl_start:tbl_end + len("</table>")]

    records: list[CoffinDayRoom] = []
    for row_m in _ROW_RE.finditer(table_html):
        row_html = row_m.group(1)
        date_m = _COFFIN_DATE_TH_RE.search(row_html)
        if not date_m:
            continue
        month, day = int(date_m.group(1)), int(date_m.group(2))
        # The query window may straddle a year boundary; for our 7-day use case
        # this is fine because all 7 rows share the same year as `query_year`.
        date_str = f"{query_year}/{month:02d}/{day:02d}"

        tds = _TD_RE.findall(row_html)
        for col_idx, cell_html in enumerate(tds, start=1):
            if not cell_html.strip():
                continue
            room_number = f"{col_idx:02d}"
            for person_m in _COFFIN_PERSON_RE.finditer(cell_html):
                colour, name, age, residence, mortician = person_m.groups()
                records.append(CoffinDayRoom(
                    occupancy_date=date_str,
                    room_number=room_number,
                    name=_strip_tags(name),
                    age=_strip_tags(age or ""),
                    gender=_coffin_gender(colour),
                    residence=_strip_tags(residence),
                    mortician=_strip_tags(mortician),
                    unit=unit_name,
                ))
    return records


_COFFIN_HALL_RE = re.compile(r"^停棺(\d{1,2})號$")


def merge_coffin_into_farewell(
    farewells: list[FarewellRecord],
    coffin: list[CoffinDayRoom],
) -> None:
    """Join coffin matrix into farewells by (unit, name) and fill
    visit_start_date / visit_end_date / visit_location / visit_note in place.

    Three outcomes per farewell record:
    1. Matched in coffin matrix -> visiting window published, fields fully set.
    2. No match but farewell venue is itself a coffin room (停棺NN號) -> the
       farewell happens in the room and prior visiting is implied; we still
       set visit_location from the venue even though no date range is public.
    3. No match and venue is a formal hall (景福廳/懷恩廳/...) -> the body
       has already moved to the hall by farewell day; no public visiting
       location. We record this in visit_note so the user knows to ask the
       family directly."""
    by_name: dict[tuple[str, str], list[CoffinDayRoom]] = {}
    for c in coffin:
        if c.name == "不公開":
            continue
        by_name.setdefault((c.unit, c.name), []).append(c)

    for f in farewells:
        rooms = by_name.get((f.unit, f.name))
        if rooms:
            dates_sorted = sorted(rooms, key=lambda r: r.occupancy_date)
            first = dates_sorted[0].occupancy_date
            # Visiting window = first day in coffin matrix ~ day before farewell.
            # If the matrix only shows the farewell day or later, there is no
            # advance window — visit_end_date collapses to visit_start_date.
            last_before = ""
            for r in dates_sorted:
                if r.occupancy_date < f.farewell_date:
                    last_before = r.occupancy_date
            f.visit_start_date = first
            f.visit_end_date = last_before or first
            room_set = sorted({r.room_number for r in dates_sorted})
            f.visit_location = " / ".join(f"{f.unit} 停柩室 {n} 號" for n in room_set)
            f.visit_note = "對應停柩室公開資料"
            continue

        hall_m = _COFFIN_HALL_RE.match(f.hall)
        if hall_m:
            room_no = f"{int(hall_m.group(1)):02d}"
            f.visit_location = f"{f.unit} 停柩室 {room_no} 號"
            f.visit_note = "告別式直接在停柩室現場;提早致意可至該停柩室"
        else:
            f.visit_location = f"{f.unit} {f.hall}"
            f.visit_note = "正式禮廳;提早致意期間/地點未公開,請逕詢家屬或禮儀業者"
