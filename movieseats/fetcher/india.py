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
    cookies: str = ""  # browser cookies for seat API auth


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
    movie_url = ""

    try:
        city_slug = INDIA_CITIES.get(city.lower().strip(), city.lower().strip().replace(" ", "-"))

        # Step 1: Find movie URL from /movies page
        await page.goto(f"{DISTRICT_BASE}/movies", wait_until="domcontentloaded", timeout=30000)
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

        # Step 2: Load movie page
        movie_url = f"{DISTRICT_BASE}/movies/{movie_path}"
        logger.info("Loading: %s", movie_url)
        await page.goto(movie_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Step 3: Parse theaters + showtimes directly from page text
        # (__NEXT_DATA__ is incomplete — late night shows loaded via XHR)
        import re
        page_text = await page.inner_text("body")
        content_id = ""

        # Extract content ID from __NEXT_DATA__ (still useful for this)
        try:
            next_data = await page.evaluate("""() => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? JSON.parse(el.textContent) : null;
            }""")
            if next_data:
                content_id = next_data.get("props", {}).get("pageProps", {}).get("data", {}).get("contentId", "")
        except Exception:
            pass

        # Parse theaters and showtimes from page text
        lines = [l.strip() for l in page_text.split("\n") if l.strip()]
        current_theater = ""
        current_distance = ""

        total_picked = 0
        theaters_picked = 0
        theater_showtime_count: dict[str, int] = {}

        for i, line in enumerate(lines):
            if theaters_picked >= MAX_THEATERS or total_picked >= MAX_TOTAL_SHOWTIMES:
                break

            # Detect theater names
            if re.match(r'.*(PVR|INOX|Cinepolis|Cinépolis|Miraj|Asian|Carnival|Roongta|Sree|Shiva)', line, re.IGNORECASE) and len(line) < 80:
                current_theater = line
                current_distance = ""
                if i + 1 < len(lines) and re.search(r'\d+\.?\d*\s*km', lines[i + 1], re.IGNORECASE):
                    current_distance = lines[i + 1]
                if current_theater not in theater_showtime_count:
                    theater_showtime_count[current_theater] = 0

            # Detect showtimes
            time_match = re.match(r'^(\d{2}:\d{2}\s*[AP]M)$', line, re.IGNORECASE)
            if time_match and current_theater:
                if theater_showtime_count.get(current_theater, 0) >= 2:
                    continue  # max 2 per theater

                time_display = time_match.group(1)

                # Detect format
                fmt = "Standard"
                if i + 1 < len(lines):
                    nxt = lines[i + 1]
                    if "DOLBY" in nxt or "Atmos" in nxt: fmt = "Dolby Atmos"
                    elif "IMAX" in nxt: fmt = "IMAX"
                    elif "4DX" in nxt: fmt = "4DX"
                    elif "3D" in nxt: fmt = "3D"

                sessions.append(IndiaCinemaSession(
                    cinema_id=0,
                    session_id="",
                    provider_id=0,
                    movie_code="",
                    content_id=content_id,
                    cinema_name=current_theater,
                    show_time="",
                    time_display=time_display,
                    format=fmt,
                    distance_km=float(re.search(r'(\d+\.?\d*)', current_distance).group(1)) if current_distance and re.search(r'(\d+\.?\d*)', current_distance) else 0,
                    seats_available=0,
                    seats_total=0,
                    price=0,
                ))

                theater_showtime_count[current_theater] = theater_showtime_count.get(current_theater, 0) + 1
                if theater_showtime_count[current_theater] == 1:
                    theaters_picked += 1
                total_picked += 1

        # Get cookies from browser — needed for seat API auth
        browser_cookies = await page.context.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in browser_cookies)
        logger.info("Got %d cookies for seat API", len(browser_cookies))
        for s in sessions:
            s.cookies = cookie_str

        logger.info("Discovered %d showtimes across %d theaters in %s", len(sessions), theaters_picked, city)

    except Exception as e:
        logger.error("India discovery failed: %s", e)
    finally:
        await page.close()

    return sessions, content_id, movie_url


async def fetch_india_seats_browser(
    context: BrowserContext,
    sessions: list[IndiaCinemaSession],
    movie_url: str,
) -> list[tuple[Showtime, SeatMap]]:
    """Fetch seat maps by clicking showtimes in parallel browser tabs.

    Uses Playwright to click each showtime and capture the seat API JSON response.
    Runs 4 tabs in parallel for speed.
    """
    results: list[tuple[Showtime, SeatMap]] = []
    semaphore = asyncio.Semaphore(4)

    async def fetch_one(sess: IndiaCinemaSession) -> tuple[Showtime, SeatMap] | None:
        async with semaphore:
            page = await context.new_page()
            seat_json = [None]

            async def on_response(response):
                if "select-seat" in response.url:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        try:
                            seat_json[0] = await response.json()
                        except Exception:
                            pass

            async def on_any_response(response):
                url = response.url
                if "select-seat" in url:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct and not seat_json[0]:  # only capture FIRST response
                        try:
                            data = await response.json()
                            if data.get("seatLayout"):  # only keep if has seat data
                                seat_json[0] = data
                                logger.info("Captured seat API for %s", sess.cinema_name)
                        except Exception:
                            pass

            page.on("response", on_any_response)

            try:
                # Load movie page
                await page.goto(movie_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1500)

                # Remove overlay
                try:
                    await page.evaluate('document.querySelector(".BottomSheet_container__4XCDW")?.remove()')
                except Exception:
                    pass

                # Click the specific showtime — use nth match to handle duplicates
                try:
                    locator = page.get_by_text(sess.time_display, exact=True)
                    count = await locator.count()
                    if count > 0:
                        await locator.first.click(force=True, timeout=5000)
                        logger.info("Clicked %s (found %d matches)", sess.time_display, count)
                    else:
                        logger.warning("No match for %s", sess.time_display)
                        await page.close()
                        return None
                    await page.wait_for_timeout(5000)
                except Exception as e:
                    logger.warning("Click failed for %s: %s", sess.time_display, str(e)[:60])
                    await page.close()
                    return None

                if not seat_json[0]:
                    logger.warning("No seat JSON captured for %s %s (URL: %s)", sess.cinema_name, sess.time_display, page.url[:80])
                    await page.close()
                    return None

                # Parse seat layout from JSON
                data = seat_json[0]
                seat_layout = data.get("seatLayout", {})
                obj_areas = seat_layout.get("colAreas", {}).get("objArea", [])
                total_rows_found = sum(len(a.get("objRow", [])) for a in obj_areas)
                logger.info("Seat data for %s: %d areas, %d rows", sess.cinema_name, len(obj_areas), total_rows_found)
                if obj_areas and not total_rows_found:
                    # Log first area structure to debug
                    first_area = obj_areas[0]
                    logger.info("  Area keys: %s", list(first_area.keys())[:10])

                rows_list: list[list[Seat]] = []
                for area in obj_areas:
                    for row_data in area.get("objRow", []):
                        row_letter = row_data.get("PhyRowId", "")
                        if not row_letter or len(row_letter) > 2:
                            continue

                        row_seats: list[Seat] = []
                        for seat_data in row_data.get("objSeat", []):
                            # District.in uses "seatNumber" or "SeatNum" or "GridSeatNum"
                            seat_num = seat_data.get("seatNumber") or seat_data.get("SeatNum") or seat_data.get("GridSeatNum") or 0
                            if not seat_num:
                                continue
                            # SeatStatus is a STRING: "0"=available, "1"=sold
                            status_str = str(seat_data.get("SeatStatus", "1"))
                            status = "available" if status_str == "0" else "taken"
                            row_seats.append(Seat(row=row_letter, number=int(seat_num), status=status))

                        if row_seats:
                            regular = [s for s in row_seats if s.status in ("available", "taken")]
                            if regular:
                                rows_list.append(sorted(row_seats, key=lambda s: s.number))

                await page.close()

                total_seats = sum(len(r) for r in rows_list)
                avail_seats = sum(1 for r in rows_list for s in r if s.status == "available")
                logger.info("  Parsed %d rows, %d total seats, %d available for %s", len(rows_list), total_seats, avail_seats, sess.cinema_name)

                if not rows_list:
                    return None

                seat_map = SeatMap(
                    rows=rows_list,
                    total_rows=len(rows_list),
                    max_seats_per_row=max(len(r) for r in rows_list),
                )

                # Get price from API response
                price = sess.price
                try:
                    ticket_types = data.get("ticketTypes", [])
                    if ticket_types:
                        price = float(ticket_types[0].get("price", sess.price))
                except Exception:
                    pass

                showtime = Showtime(
                    time=sess.time_display,
                    date=sess.show_time.split("T")[0] if "T" in sess.show_time else "",
                    format=sess.format,
                    price=price,
                    theater_name=sess.cinema_name,
                    chain="district.in",
                    url=movie_url,
                )

                total = sum(len(r) for r in rows_list)
                avail = sum(1 for r in rows_list for s in r if s.status == "available")
                logger.info("  %s %s: %d/%d available", sess.cinema_name, sess.time_display, avail, total)

                return (showtime, seat_map)

            except Exception as e:
                logger.warning("India seat fetch failed for %s: %s", sess.cinema_name, str(e)[:60])
                try:
                    await page.close()
                except Exception:
                    pass
                return None

    # Fetch all in parallel (4 tabs)
    tasks = [fetch_one(s) for s in sessions]
    results_raw = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results_raw:
        if isinstance(r, tuple):
            results.append(r)

    logger.info("Fetched %d/%d seat maps via browser", len(results), len(sessions))
    return results
