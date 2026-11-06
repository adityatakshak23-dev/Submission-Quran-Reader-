import asyncio, os
from pathlib import Path
import aiohttp
DATA_DIR=Path(os.getenv("DATA_DIR","./data"))
DATA_DIR.mkdir(parents=True,exist_ok=True)
class SetupError(ValueError): pass
QURAN_TEXT_URL = "https://submission.org/QI2d/QI2_EN_data"
QURAN_CACHE_FILE = DATA_DIR / "quran_inspector_english.txt"
QURAN_COUNTS = (7,286,200,176,120,165,206,75,127,109,123,111,43,52,99,128,111,110,98,135,112,78,118,64,77,227,93,88,69,60,34,30,73,54,45,83,182,88,75,85,54,53,89,59,37,35,38,29,18,45,60,49,62,55,78,96,29,22,24,13,14,11,11,18,12,12,30,52,52,44,28,28,20,56,40,31,50,40,46,42,29,19,36,25,22,17,19,26,30,20,15,21,11,8,8,19,5,8,8,11,11,8,3,9,5,4,7,3,6,3,5,4,5,6)
quran_text_cache = None
reader_lock = asyncio.Lock()


def validate_reference(chapter, verse):
    if (type(chapter) is not int or type(verse) is not int or not 1 <= chapter <= 114
            or not 1 <= verse <= QURAN_COUNTS[chapter - 1]):
        raise SetupError("That verse is not in this edition. Enter a valid chapter and verse.")


def adjacent_reference(chapter, verse, direction):
    validate_reference(chapter, verse)
    if direction == 1:
        if verse < QURAN_COUNTS[chapter - 1]:
            return chapter, verse + 1
        if chapter < 114:
            return chapter + 1, 1
    elif direction == -1:
        if verse > 1:
            return chapter, verse - 1
        if chapter > 1:
            return chapter - 1, QURAN_COUNTS[chapter - 2]
    raise SetupError("You are at the beginning or end of the Quran.")


def parse_quran_text(raw):
    # Inspector numbers its verse records with 112 separate Basmala records.
    rows = {}
    for line in raw.splitlines():
        parts = line.split("|")
        if parts[0] != "v":
            continue
        if len(parts) < 3 or not parts[1].isdigit():
            raise ValueError("Invalid Quran source row")
        index, text = int(parts[1]), parts[2].strip()
        if index in rows or not text or len(text) > 3500 or "<" in text:
            raise ValueError("Invalid or duplicate Quran verse")
        rows[index] = text
    if set(rows) != set(range(1, 6347)):
        raise ValueError("Incomplete Quran source")
    verses = {}
    offset = 0
    for chapter, count in enumerate(QURAN_COUNTS, 1):
        for verse in range(1, count + 1):
            verses[(chapter, verse)] = rows[offset + verse]
        offset += count + (1 if chapter + 1 not in (9, 115) else 0)
    if len(verses) != 6234 or verses[(42, 43)] != "Resorting to patience and forgiveness reflects a true strength of character.":
        raise ValueError("Unexpected Quran source format or translation")
    return verses


async def get_quran_text():
    global quran_text_cache
    if quran_text_cache is not None:
        return quran_text_cache
    if QURAN_CACHE_FILE.exists():
        try:
            quran_text_cache = parse_quran_text(QURAN_CACHE_FILE.read_text(encoding="utf-8"))
            return quran_text_cache
        except (ValueError, OSError):
            raise SetupError("The saved Quran text could not be validated. Ask the maintainer to check it.")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), trust_env=True) as session:
            async with session.get(QURAN_TEXT_URL) as response:
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > 3_000_000:
                        raise ValueError("Quran source too large")
                    chunks.append(chunk)
                raw = b"".join(chunks).decode("utf-8-sig")
        data = parse_quran_text(raw)
        temporary = QURAN_CACHE_FILE.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, QURAN_CACHE_FILE)
        quran_text_cache = data
        return data
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError) as error:
        raise SetupError("Quran text could not be loaded. Please retry /quran.") from error

