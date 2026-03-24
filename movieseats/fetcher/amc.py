"""AMC Theatres fetcher via Playwright.

No API key needed. Uses:
- Theater showtimes page: /movie-theatres/{market}/{slug}/showtimes
- Seat selection page: /showtimes/{id}/seats
- Seats from: input[aria-label*="Seat"] + disabled attribute
"""

from __future__ import annotations

import asyncio
import logging
import re

import aiohttp
from playwright.async_api import BrowserContext

from movieseats.seats.models import Seat, SeatMap, Showtime

logger = logging.getLogger(__name__)

AMC_BASE = "https://www.amctheatres.com"

# Seed theaters — one per major US market. Used to discover nearby theaters.
AMC_SEED_THEATERS = {
    # Texas
    "75": "dallas-ft-worth/amc-stonebriar-24",
    "760": "dallas-ft-worth/amc-stonebriar-24",
    "770": "houston/amc-houston-8",
    "786": "san-antonio/amc-rivercenter-11",
    "787": "austin/amc-barton-creek-14",
    # California
    "900": "los-angeles/amc-century-city-15",
    "902": "los-angeles/amc-century-city-15",
    "910": "los-angeles/amc-burbank-16",
    "920": "san-diego/amc-mission-valley-20",
    "940": "san-francisco/amc-metreon-16",
    "950": "san-jose/amc-eastridge-15",
    # Northeast
    "100": "new-york/amc-empire-25",
    "070": "new-jersey/amc-garden-state-16",
    "080": "new-jersey/amc-garden-state-16",
    "190": "philadelphia/amc-neshaminy-24",
    "021": "boston/amc-boston-common-19",
    # Midwest
    "606": "chicago/amc-river-east-21",
    "600": "chicago/amc-river-east-21",
    # Southeast
    "303": "atlanta/amc-phipps-plaza-14",
    "330": "south-florida/amc-aventura-24",
    "336": "tampa-bay-fl/amc-veterans-24",
    # Pacific Northwest
    "980": "seattle-tacoma/amc-pacific-place-11",
    "970": "portland-or/amc-lloyd-center-10",
    # Other
    "850": "phoenix/amc-arizona-center-24",
    "802": "denver/amc-westminster-promenade-24",
    "160": "pittsburgh/amc-waterfront-22",
    "270": "raleigh-durham/amc-southpoint-17",
}

MAX_THEATERS = 5
MAX_SHOWTIMES_PER_THEATER = 3


async def find_amc_theaters_and_seats(
    context: BrowserContext,
    zipcode: str,
    movie_name: str,
) -> list[tuple[Showtime, SeatMap]]:
    """Find AMC theaters near zipcode and get seat data for a movie.

    1. Find seed theater from zipcode prefix
    2. HTTP fetch theater page → discover nearby AMC theaters
    3. Playwright: load each theater showtimes page → find movie + showtime IDs
    4. Playwright: navigate to seat pages → parse aria-label inputs
    """
    seat_data: list[tuple[Showtime, SeatMap]] = []

    # Step 1: Find seed theater from zipcode
    seed = None
    for prefix_len in [3, 2]:
        prefix = zipcode[:prefix_len]
        if prefix in AMC_SEED_THEATERS:
            seed = AMC_SEED_THEATERS[prefix]
            break

    if not seed:
        # Try first 2 digits
        prefix2 = zipcode[:2]
        for k, v in AMC_SEED_THEATERS.items():
            if k.startswith(prefix2):
                seed = v
                break

    if not seed:
        logger.warning("No AMC seed theater for zipcode %s", zipcode)
        return []

    logger.info("AMC seed theater: %s", seed)

    # Step 2: Discover nearby theaters via HTTP
    nearby_slugs = await _discover_nearby_theaters(seed)
    if not nearby_slugs:
        nearby_slugs = [seed]

    nearby_slugs = nearby_slugs[:MAX_THEATERS]
    logger.info("Found %d AMC theaters near %s", len(nearby_slugs), zipcode)

    # Step 3: For each theater, find showtimes for the movie
    movie_lower = movie_name.lower()
    all_showtime_ids: list[tuple[str, str, str]] = []  # (theater_name, showtime_id, time_display)

    page = await context.new_page()
    try:
        for market_slug in nearby_slugs:
            slug = market_slug.split("/")[-1]
            url = f"{AMC_BASE}/movie-theatres/{market_slug}/showtimes?date=2026-03-24"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)

                # Find showtimes for our movie
                data = await page.evaluate(r"""(movieName) => {
                    const results = [];
                    const text = document.body.innerText;
                    const lines = text.split('\n').map(l => l.trim()).filter(l => l);
                    const words = movieName.toLowerCase().split(/\s+/).filter(w => w.length > 3);

                    let inMovie = false;
                    let theaterName = '';

                    // Get theater name from page title or header
                    const titleEl = document.querySelector('h1, [class*="theatre-name"]');
                    theaterName = titleEl ? titleEl.innerText.trim() : '';

                    // Find showtimes that are links with IDs
                    const links = document.querySelectorAll('a[href*="/showtimes/"]');
                    const movieShowtimes = [];

                    // First find if our movie is on this page
                    const movieFound = words.some(w => text.toLowerCase().includes(w));
                    if (!movieFound) return {theater: theaterName, showtimes: []};

                    // Get all showtime links
                    links.forEach(a => {
                        const href = a.href;
                        const match = href.match(/\/showtimes\/(\d+)/);
                        const timeText = a.innerText.trim();
                        if (match && timeText.match(/\d{1,2}:\d{2}[ap]m/i)) {
                            movieShowtimes.push({
                                id: match[1],
                                time: timeText.match(/(\d{1,2}:\d{2}[ap]m)/i)?.[1] || timeText,
                            });
                        }
                    });

                    return {theater: theaterName, showtimes: movieShowtimes};
                }""", movie_name)

                theater_name = data.get("theater", slug)
                showtimes = data.get("showtimes", [])

                logger.info("  AMC %s: %d showtimes", theater_name, len(showtimes))

                for st in showtimes[:MAX_SHOWTIMES_PER_THEATER]:
                    all_showtime_ids.append((theater_name, st["id"], st["time"]))

            except Exception as e:
                logger.warning("AMC theater %s failed: %s", slug, str(e)[:60])
    finally:
        await page.close()

    if not all_showtime_ids:
        logger.info("No AMC showtimes found for %s", movie_name)
        return []

    logger.info("Found %d AMC showtimes total, fetching seats...", len(all_showtime_ids))

    # Step 4: Fetch seat maps in parallel
    semaphore = asyncio.Semaphore(4)

    async def fetch_one_amc_seat(theater_name: str, showtime_id: str, time_display: str):
        async with semaphore:
            seat_page = await context.new_page()
            try:
                url = f"{AMC_BASE}/showtimes/{showtime_id}/seats"
                await seat_page.goto(url, wait_until="networkidle", timeout=20000)
                await seat_page.wait_for_timeout(3000)

                # Parse seats from aria-label inputs
                raw_seats = await seat_page.evaluate(r"""() => {
                    const inputs = document.querySelectorAll('input[aria-label*="Seat"]');
                    return Array.from(inputs).map(el => {
                        const label = el.getAttribute('aria-label') || '';
                        const disabled = el.disabled;
                        const match = label.match(/Seat ([A-Z])(\d+)/);
                        if (!match) return null;
                        return {
                            row: match[1],
                            number: parseInt(match[2]),
                            available: !disabled,
                        };
                    }).filter(s => s !== null);
                }""")

                await seat_page.close()

                if not raw_seats:
                    return None

                # Build SeatMap
                rows_dict: dict[str, list[Seat]] = {}
                for s in raw_seats:
                    seat = Seat(
                        row=s["row"],
                        number=s["number"],
                        status="available" if s["available"] else "taken",
                    )
                    rows_dict.setdefault(s["row"], []).append(seat)

                rows = []
                for letter in sorted(rows_dict.keys()):
                    rows.append(sorted(rows_dict[letter], key=lambda s: s.number))

                if not rows:
                    return None

                seat_map = SeatMap(
                    rows=rows,
                    total_rows=len(rows),
                    max_seats_per_row=max(len(r) for r in rows),
                )

                showtime = Showtime(
                    time=time_display,
                    date="",
                    format="Standard",
                    price=0,
                    theater_name=theater_name,
                    chain="amc",
                    url=f"{AMC_BASE}/showtimes/{showtime_id}/seats",
                )

                total = sum(len(r) for r in rows)
                avail = sum(1 for r in rows for s in r if s.status == "available")
                logger.info("  AMC %s %s: %d/%d available", theater_name, time_display, avail, total)

                return (showtime, seat_map)

            except Exception as e:
                logger.warning("AMC seat fetch failed for %s: %s", theater_name, str(e)[:60])
                try:
                    await seat_page.close()
                except Exception:
                    pass
                return None

    tasks = [fetch_one_amc_seat(tn, sid, td) for tn, sid, td in all_showtime_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, tuple):
            seat_data.append(r)

    logger.info("AMC: fetched %d/%d seat maps", len(seat_data), len(all_showtime_ids))
    return seat_data


async def _discover_nearby_theaters(seed_market_slug: str) -> list[str]:
    """Discover nearby AMC theaters by fetching a known theater's page via HTTP."""
    try:
        url = f"{AMC_BASE}/movie-theatres/{seed_market_slug}/showtimes"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return [seed_market_slug]
                html = await resp.text()

        # Extract theater slugs from HTML
        slugs = re.findall(r'/movie-theatres/([^/]+/[^/\"\\]+)', html)
        unique = []
        seen = set()
        for s in slugs:
            clean = s.rstrip("\\")
            if clean not in seen and "showtimes" not in clean and "%5B" not in clean:
                seen.add(clean)
                unique.append(clean)

        if unique:
            logger.info("Discovered %d AMC theaters from %s", len(unique), seed_market_slug)
        return unique if unique else [seed_market_slug]

    except Exception as e:
        logger.warning("AMC discovery failed: %s", str(e)[:60])
        return [seed_market_slug]
