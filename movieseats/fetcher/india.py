"""India theater fetcher via District.in (Paytm Movies).

Optimized: extracts ALL data from __NEXT_DATA__ JSON (one page load),
then calls seat API directly via HTTP for seat maps (no Playwright for seats).
Covers ALL Indian chains: PVR, INOX, Cinepolis, Miraj, independent theaters.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

import aiohttp
from playwright.async_api import BrowserContext

from movieseats.seats.models import Seat, SeatMap, Showtime

logger = logging.getLogger(__name__)

DISTRICT_BASE = "https://www.district.in"
SEAT_API = "https://www.district.in/gw/consumer/movies/v1/select-seat?version=3&site_id=1&channel=web&child_site_id=1&platform=district"

INDIA_CITIES = {
    "hyderabad": "hyderabad", "mumbai": "mumbai", "delhi": "delhi-ncr",
    "bangalore": "bengaluru", "bengaluru": "bengaluru", "chennai": "chennai",
    "kolkata": "kolkata", "pune": "pune", "ahmedabad": "ahmedabad",
    "jaipur": "jaipur", "lucknow": "lucknow", "kochi": "kochi",
    "chandigarh": "chandigarh", "indore": "indore", "bhopal": "bhopal",
    "vizag": "visakhapatnam", "visakhapatnam": "visakhapatnam",
    "noida": "delhi-ncr", "gurgaon": "delhi-ncr", "gurugram": "delhi-ncr",
    "new delhi": "delhi-ncr", "navi mumbai": "mumbai", "thane": "mumbai",
    "gachibowli": "hyderabad", "secunderabad": "hyderabad",
}

MAX_THEATERS = 8
MAX_TOTAL_SHOWTIMES = 15


@dataclass
class IndiaCinemaSession:
    """All data needed to call the seat API."""
    cinema_id: int
    session_id: str
    provider_id: int
    movie_code: str
    content_id: str
    cinema_name: str
    show_time: str  # "2026-03-23T16:30"
    time_display: str  # "4:30 PM"
    format: str
    distance_km: float
    seats_available: int
    seats_total: int
    price: float


async def discover_india_showtimes(
    context: BrowserContext,
    city: str,
    movie_name: str,
) -> tuple[list[IndiaCinemaSession], str]:
    """Discover all theaters and showtimes from ONE page load.

    Extracts __NEXT_DATA__ JSON from the movie page.
    Returns (list of sessions, content_id).
    """
    page = await context.new_page()
    sessions: list[IndiaCinemaSession] = []
    content_id = ""

    try:
        city_slug = INDIA_CITIES.get(city.lower().strip(), city.lower().strip().replace(" ", "-"))

        # Step 1: Find movie URL from /movies page
        await page.goto(f"{DISTRICT_BASE}/movies", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(2000)

        movie_path = await page.evaluate(r"""(params) => {
            const name = params.name;
            const city = params.city;
            const links = document.querySelectorAll('a[href*="/movies/"]');
            const words = name.toLowerCase().split(/\s+/).filter(w => w.length > 2);
            const matches = [];

            links.forEach(link => {
                const text = link.innerText.toLowerCase();
                const href = link.href.toLowerCase();
                const isMatch = words.some(w => w.length > 3 && (text.includes(w) || href.includes(w)));
                if (isMatch && href.includes('ticket')) {
                    const pathMatch = link.href.match(/\/movies\/([^?]+)/);
                    if (pathMatch) matches.push({slug: pathMatch[1], href: link.href});
                }
            });

            // Prefer city-specific link
            for (const m of matches) {
                if (m.slug.includes('-in-' + city)) return m.slug;
            }
            // Replace city in first match
            if (matches.length > 0) {
                const first = matches[0].slug;
                const cityMatch = first.match(/-in-([a-z-]+)-MV/);
                if (cityMatch) return first.replace('-in-' + cityMatch[1] + '-MV', '-in-' + city + '-MV');
                const mvMatch = first.match(/-MV(\d+)$/);
                if (mvMatch) return first.replace('-MV' + mvMatch[1], '-in-' + city + '-MV' + mvMatch[1]);
                return first;
            }
            return null;
        }""", {"name": movie_name, "city": city_slug})

        if not movie_path:
            logger.error("Movie not found on District.in: %s in %s", movie_name, city)
            return [], ""

        # Step 2: Load movie page and extract __NEXT_DATA__
        movie_url = f"{DISTRICT_BASE}/movies/{movie_path}"
        logger.info("Loading: %s", movie_url)
        await page.goto(movie_url, wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(2000)

        next_data = await page.evaluate("""() => {
            const el = document.getElementById('__NEXT_DATA__');
            return el ? JSON.parse(el.textContent) : null;
        }""")

        if not next_data:
            logger.error("No __NEXT_DATA__ on movie page")
            return [], ""

        # Step 3: Parse all theaters and showtimes
        server_state = next_data.get("props", {}).get("pageProps", {}).get("data", {})
        content_id = server_state.get("contentId", "")

        movie_sessions = server_state.get("serverState", {}).get("movieSessions", {})
        if not movie_sessions:
            logger.error("No movieSessions in data")
            return [], ""

        # Get the first format group (usually Hindi)
        format_key = list(movie_sessions.keys())[0]
        arranged = movie_sessions[format_key].get("arrangedSessions", [])

        # Get cinema names from meta
        cinema_meta = movie_sessions[format_key].get("meta", {}).get("entityMetaData", {})

        total_picked = 0
        theaters_picked = 0

        for cinema in arranged:
            if theaters_picked >= MAX_THEATERS or total_picked >= MAX_TOTAL_SHOWTIMES:
                break

            c = cinema.get("data", {})
            cinema_id = c.get("id", 0)
            distance = c.get("distanceFromUser", 0)
            cinema_name = ""  # Will get from page text

            cinema_sessions = cinema.get("sessions", [])
            if not cinema_sessions:
                continue

            picked_for_theater = 0
            for sess in cinema_sessions:
                if total_picked >= MAX_TOTAL_SHOWTIMES or picked_for_theater >= 2:
                    break

                sid = sess.get("sid", "")
                pid = sess.get("pid", 0)
                mid = sess.get("mid", "")
                show_time = sess.get("showTime", "")

                # Parse time display
                time_display = ""
                if "T" in show_time:
                    time_part = show_time.split("T")[1]
                    hour, minute = int(time_part.split(":")[0]), time_part.split(":")[1]
                    ampm = "AM" if hour < 12 else "PM"
                    dh = hour if hour <= 12 else hour - 12
                    if dh == 0:
                        dh = 12
                    time_display = f"{dh}:{minute} {ampm}"

                # Get availability from areas
                total_avail = 0
                total_seats = 0
                price = 0
                fmt = "Standard"
                for area in sess.get("areas", []):
                    total_avail += area.get("sAvail", 0)
                    total_seats += area.get("sTotal", 0)
                    if not price:
                        price = area.get("price", 0) or 0
                    label = area.get("label", "").lower()
                    if "dolby" in label or "atmos" in label:
                        fmt = "Dolby Atmos"
                    elif "imax" in label:
                        fmt = "IMAX"
                    elif "4dx" in label:
                        fmt = "4DX"

                sessions.append(IndiaCinemaSession(
                    cinema_id=cinema_id,
                    session_id=str(sid),
                    provider_id=pid,
                    movie_code=mid,
                    content_id=content_id,
                    cinema_name="",  # filled later
                    show_time=show_time,
                    time_display=time_display,
                    format=fmt,
                    distance_km=distance,
                    seats_available=total_avail,
                    seats_total=total_seats,
                    price=float(price),
                ))

                total_picked += 1
                picked_for_theater += 1

            if picked_for_theater > 0:
                theaters_picked += 1

        # Get cinema names from the page text
        cinema_names = await page.evaluate(r"""() => {
            const text = document.body.innerText;
            const lines = text.split('\n').map(l => l.trim()).filter(l => l);
            const names = {};
            for (const line of lines) {
                if (line.match(/(PVR|INOX|Cinepolis|Cinépolis|Miraj|Asian|Carnival|Roongta|Sree|Shiva|AMB |SPI |Fun |Gold )/i) && line.length < 80) {
                    names[line] = true;
                }
            }
            return Object.keys(names);
        }""")

        # Map cinema names to sessions by order
        name_idx = 0
        last_cid = None
        for sess in sessions:
            if sess.cinema_id != last_cid:
                if name_idx < len(cinema_names):
                    sess.cinema_name = cinema_names[name_idx]
                    name_idx += 1
                else:
                    sess.cinema_name = f"Cinema {sess.cinema_id}"
                last_cid = sess.cinema_id
            else:
                if name_idx > 0:
                    sess.cinema_name = cinema_names[name_idx - 1]

        logger.info("Discovered %d showtimes across %d theaters in %s", len(sessions), theaters_picked, city)

    except Exception as e:
        logger.error("India discovery failed: %s", e)
    finally:
        await page.close()

    return sessions, content_id


async def fetch_india_seats_http(
    sessions: list[IndiaCinemaSession],
) -> list[tuple[Showtime, SeatMap]]:
    """Fetch seat maps via direct HTTP API calls (no Playwright needed!).

    Calls District.in's seat API in parallel for each session.
    """
    results: list[tuple[Showtime, SeatMap]] = []
    semaphore = asyncio.Semaphore(6)

    async def fetch_one(sess: IndiaCinemaSession) -> tuple[Showtime, SeatMap] | None:
        async with semaphore:
            payload = {
                "cinemaId": sess.cinema_id,
                "sessionId": sess.session_id,
                "providerId": sess.provider_id,
                "screenOnTop": True,
                "freeSeating": False,
                "screenFormat": "2D",
                "moviecode": sess.movie_code,
                "contentId": sess.content_id,
                "config": {"socialDistancing": 1},
            }

            try:
                async with aiohttp.ClientSession() as http:
                    async with http.post(
                        SEAT_API,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status != 200:
                            logger.warning("Seat API %d for %s", resp.status, sess.cinema_name)
                            return None
                        data = await resp.json()

                seat_layout = data.get("seatLayout", {})
                obj_areas = seat_layout.get("colAreas", {}).get("objArea", [])

                rows_list: list[list[Seat]] = []
                for area in obj_areas:
                    for row_data in area.get("objRow", []):
                        row_letter = row_data.get("PhyRowId", "")
                        if not row_letter or len(row_letter) > 2:
                            continue

                        row_seats: list[Seat] = []
                        for seat_data in row_data.get("objSeat", []):
                            seat_num = seat_data.get("SeatNum", 0)
                            if not seat_num:
                                continue
                            status_code = seat_data.get("SeatStatus", 1)
                            status = "available" if status_code == 0 else "taken"
                            row_seats.append(Seat(row=row_letter, number=seat_num, status=status))

                        if row_seats:
                            regular = [s for s in row_seats if s.status in ("available", "taken")]
                            if regular:
                                rows_list.append(sorted(row_seats, key=lambda s: s.number))

                if not rows_list:
                    return None

                seat_map = SeatMap(
                    rows=rows_list,
                    total_rows=len(rows_list),
                    max_seats_per_row=max(len(r) for r in rows_list),
                )

                showtime = Showtime(
                    time=sess.time_display,
                    date=sess.show_time.split("T")[0] if "T" in sess.show_time else "",
                    format=sess.format,
                    price=sess.price,
                    theater_name=sess.cinema_name,
                    chain="district.in",
                    url=f"{DISTRICT_BASE}/movies/seat-layout",
                )

                total = sum(len(r) for r in rows_list)
                avail = sum(1 for r in rows_list for s in r if s.status == "available")
                logger.info("  %s %s: %d/%d available (HTTP)", sess.cinema_name, sess.time_display, avail, total)

                return (showtime, seat_map)

            except Exception as e:
                logger.warning("Seat API failed for %s: %s", sess.cinema_name, str(e)[:60])
                return None

    # Fetch all in parallel
    tasks = [fetch_one(s) for s in sessions]
    results_raw = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results_raw:
        if isinstance(r, tuple):
            results.append(r)

    logger.info("Fetched %d/%d seat maps via HTTP", len(results), len(sessions))
    return results
