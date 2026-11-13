"""FIR analysis: find the penal sections and the offence date in an FIR, and decide which code applies.

Pure functions only (no database, no models, no LLM), so the result is deterministic and testable.

* Sections are recognised in English, Hindi, Marathi, Bengali and Punjabi FIR text, including the
  police shorthand ``498A/406/34 IPC``, ``धारा 302, 34 भा.दं.सं.`` and ``कलम 420 भादंवि``.
  Native digits (०-९, ০-৯, ੦-੯) are read as ASCII digits.
* The Bharatiya Nyaya Sanhita (BNS) replaced the Indian Penal Code (IPC) for offences committed on
  or after 1 July 2024. Sections without an explicit code label are assigned by the offence date.
"""

import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

BNS_COMMENCEMENT = date(2024, 7, 1)

DATA_FILE = Path(__file__).parent / "data" / "offences.json"

# ── code (Act) names ──
_IPC = (
    r"i\s*\.?\s*p\s*\.?\s*c\b\.?"
    r"|indian\s+penal\s+code"
    r"|code\s+p[ée]nal\s+indien"
    r"|भा\s*\.?\s*द(?:ं|ण्)?\s*\.?\s*(?:सं|वि)\s*\.?"  # भा.दं.सं. / भा.द.वि. / भादंवि / भादंसं
    r"|भारतीय\s+द(?:ं|ण्)ड\s+(?:संहिता|विधान)"
    r"|आई\s*\.?\s*पी\s*\.?\s*सी\s*\.?"
    r"|ভারতীয়\s+দণ্ডবিধি|ভাঃ\s*দঃ\s*বিঃ|আই\s*\.?\s*পি\s*\.?\s*সি"
    r"|ਭਾਰਤੀ\s+ਦੰਡ\s+ਸੰਹਿਤਾ|ਆਈ\s*\.?\s*ਪੀ\s*\.?\s*ਸੀ"
)
_BNS = (
    r"b\s*\.?\s*n\s*\.?\s*s\b(?!\s*\.?\s*s)\.?"  # BNS, but not BNSS (procedure)
    r"|bharatiya\s+nyaya\s+sanhita"
    r"|भारतीय\s+न्याय\s+संहिता"
    r"|भा\s*\.?\s*न्या\s*\.?\s*सं\s*\.?"
    r"|बी\s*\.?\s*एन\s*\.?\s*एस\s*\.?(?!\s*एस)"
    r"|ভারতীয়\s+ন্যায়\s+সংহিতা|বি\s*\.?\s*এন\s*\.?\s*এস"
    r"|ਭਾਰਤੀ\s+ਨਿਆਂ\s+ਸੰਹਿਤਾ|ਬੀ\s*\.?\s*ਐਨ\s*\.?\s*ਐਸ"
)
# Procedure codes: sections of these are not offences, so they are skipped.
_PROC = (
    r"cr\s*\.?\s*p\s*\.?\s*c(?![a-z])\.?|b\s*\.?\s*n\s*\.?\s*s\s*\.?\s*s(?![a-z])\.?"
    r"|code\s+of\s+criminal\s+procedure|bharatiya\s+nagarik\s+suraksha\s+sanhita"
    r"|द(?:ं|ण्)ड\s+प्रक्रिया\s+संहिता|दं?\s*\.?\s*प्र\s*\.?\s*सं\s*\.?"
    r"|नागरिक\s+सुरक्षा\s+संहिता|फौजदारी\s+प्रक्रिया\s+संहिता|फौ\s*\.?\s*प्र\s*\.?\s*सं\s*\.?"
)
_ACT_RE = re.compile(rf"(?P<proc>{_PROC})|(?P<ipc>{_IPC})|(?P<bns>{_BNS})", re.IGNORECASE)
# Another statute named after a section list, e.g. "135(1)(A) of Electricity Act 2003".
_OTHER_ACT_RE = re.compile(
    r"\s*(?:of\s+(?:the\s+)?)?(?P<name>[A-Za-z][A-Za-z.&'\- ]{1,60}?\bAct\b)(?:[\s,\-]*(?P<year>\d{4}))?",
    re.IGNORECASE,
)

_SECTION_WORD = (
    r"(?:u\s*/\s*ss?\b\.?|under\s+sections?|sections?|secs?\b\.?|s\.(?=\s*\d)"
    r"|धाराओं|धारायें|धाराएं|धाराएँ|धारा|कलमे|कलम|ধারা|ਧਾਰਾਵਾਂ|ਧਾਰਾ|articles?)"
)
# Letter suffix: Latin (498A) or Devanagari (498ए, 354बी), not followed by more letters ("34 एवं").
_NUM = r"\d{1,3}(?!\d)(?:\s?(?:[A-Ea-e](?![A-Za-z])|(?:ए|बी|सी|डी)(?![ऀ-ॿ])))?(?:\s*\(\s*\d{1,2}\s*\))*(?:\s*\(\s*[A-Za-z]{1,3}\s*\))?"
_SEP = (
    r"(?:\s*[/,&+]\s*|\s+(?:and|r\s*/\s*w|read\s+with|et|और|एवं|व|तथा|आणि|सह|ও|এবং|ਅਤੇ)\s+)"
)
_LIST_RE = re.compile(rf"(?<![\d/\-])(?<!\d\.){_NUM}(?:{_SEP}{_NUM})*(?!\s*[/.\-]\s*\d)", re.IGNORECASE)
_ITEM_RE = re.compile(_NUM, re.IGNORECASE)

# Between a section list and a following code name: "302/34 IPC", "302 of the IPC", "302, 34 भा.दं.सं.".
_GAP_AFTER = re.compile(r"[\s,]*(?:of\s+(?:the\s+)?|का|की|के|च्या|चे|ची|এর)?[\s,]*", re.IGNORECASE)
# Between a code name and a following list: "IPC section 302", "भा.दं.वि. कलम 420", "BNS 103(1)".
_GAP_BEFORE = re.compile(
    rf"(?:[\s,]*(?:\d{{4}})?[\s,]*(?:की|के|का|च्या|चे|ची|এর|read\s+with|r\s*/\s*w)?\s*{_SECTION_WORD}?[\s:.\-]*)$", re.IGNORECASE
)
_SECTION_WORD_BEFORE = re.compile(rf"{_SECTION_WORD}[\s:.\-]*$", re.IGNORECASE)

# ── dates ──
_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january", "janvier"),
            ("feb", "february", "février", "fevrier"),
            ("mar", "march", "mars"),
            ("apr", "april", "avril"),
            ("may", "mai"),
            ("jun", "june", "juin"),
            ("jul", "july", "juillet"),
            ("aug", "august", "août", "aout"),
            ("sep", "sept", "september", "septembre"),
            ("oct", "october", "octobre"),
            ("nov", "november", "novembre"),
            ("dec", "december", "décembre", "decembre"),
        ],
        start=1,
    )
    for m in names
}
_NUMERIC_DATE_RE = re.compile(
    r"(?<![\d/\-])(?<!\d\.)(\d{1,2})\s*[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{4})(?![\d/\-]|\.\d)"
)
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_WORD_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?:st|nd|rd|th|er)?\s+([A-Za-zéû]{3,9})\.?,?\s+(\d{4})(?!\d)", re.IGNORECASE
)
_OCCURRENCE_RE = re.compile(
    r"occurr?ence|incident|offen[cs]e\s+(?:date|on|committed)|date\s+of\s+(?:the\s+)?offen[cs]e"
    r"|घटना|घटने|वारदात|अपराध\s+की\s+(?:तारीख|तिथि)|ঘটনা|অপরাধের|ਘਟਨਾ|faits|infraction",
    re.IGNORECASE,
)
_REPORT_RE = re.compile(
    r"date\s+(?:and\s+time\s+)?of\s+(?:report|registration|information)|reported\s+on|registered\s+on"
    r"|सूचना\s+(?:की\s+)?(?:तारीख|प्राप्त)|दर्ज|नोंद|তথ্য\s+প্রাপ্তি|ਦਰਜ",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SectionRef:
    section: str  # canonical, e.g. "498A", "103(1)", "125(b)"
    code: str | None  # "IPC" | "BNS" | None (unlabelled) | another Act's name
    label_source: str  # "explicit" | "offence_date" | "unknown" | "other_act"
    matched_text: str


@dataclass(frozen=True)
class DateCandidate:
    value: date
    text: str
    kind: str  # "occurrence" | "report" | "other"


@dataclass
class FirAnalysis:
    sections: list[SectionRef]
    offence_date: date | None
    offence_date_source: str  # "provided" | "occurrence" | "earliest" | "none"
    date_candidates: list[DateCandidate]
    applicable_code: str | None  # code chosen from the offence date
    warnings: list[str] = field(default_factory=list)


def normalise_text(text: str) -> str:
    """NFC, HTML entities (incl. OCR-mangled ``&Amp;``) and native digits to ASCII. Keeps letters intact."""
    text = re.sub(r"&amp;", "&", text, flags=re.IGNORECASE)
    text = unicodedata.normalize("NFC", html.unescape(text))
    out = []
    for ch in text:
        if not ch.isascii() and unicodedata.category(ch) == "Nd":
            out.append(str(unicodedata.digit(ch)))
        else:
            out.append(ch)
    return "".join(out).replace(" ", " ")


_DEVANAGARI_LETTERS = {"ए": "A", "बी": "B", "सी": "C", "डी": "D"}


def canonical_section(raw: str) -> str:
    """'498 a' -> '498A', '103 (1)' -> '103(1)', '125 (B)' -> '125(b)', '135(1)(A)' -> '135(1)(a)'."""
    s = re.sub(r"\s+", "", raw)
    for deva, latin in _DEVANAGARI_LETTERS.items():
        s = re.sub(rf"^(\d+){deva}", rf"\g<1>{latin}", s)
    m = re.match(r"(\d+)([A-Za-z]?)(.*)", s)
    if not m:
        return s
    number, letter, rest = m.groups()
    rest = re.sub(r"\(([A-Za-z]+)\)", lambda x: f"({x.group(1).lower()})", rest)
    return f"{number}{letter.upper()}{rest}"


def _code_of(match: re.Match[str]) -> str:
    if match.group("proc"):
        return "PROC"
    return "IPC" if match.group("ipc") else "BNS"


def detect_sections(text: str, default_code: str | None = None) -> list[SectionRef]:
    """Penal sections mentioned in ``text``, de-duplicated in order of first appearance.

    Only number lists anchored to a code name ("IPC", "भा.दं.सं.") or a section word ("u/s", "धारा",
    "कलम") are taken, so phone numbers, amounts and dates are not mistaken for sections.
    Unlabelled sections get ``default_code`` (the code in force on the offence date), if given.
    """
    text = normalise_text(text)
    found: list[SectionRef] = []
    seen: set[tuple[str, str | None]] = set()

    for lst in _LIST_RE.finditer(text):
        start, end = lst.span()
        code: str | None = None
        source = "unknown"
        # 1) "302/34 IPC" — a code name right after the list.
        gap = _GAP_AFTER.match(text, end)
        after = _ACT_RE.match(text, gap.end()) if gap and gap.end() - end <= 25 else None
        if after:
            code, source = _code_of(after), "explicit"
        else:
            # 2) "IPC section 302" — a code name shortly before the list.
            window = text[max(0, start - 45) : start]
            before = None
            for m in _ACT_RE.finditer(window):
                if _GAP_BEFORE.fullmatch(window, m.end()):
                    before = m
            if before:
                code, source = _code_of(before), "explicit"
            else:
                other = _OTHER_ACT_RE.match(text, end)
                if other and not _ACT_RE.fullmatch(other.group("name").strip()):
                    name = re.sub(r"\s+", " ", other.group("name")).strip().title()
                    if other.group("year"):
                        name = f"{name}, {other.group('year')}"
                    code, source = name, "other_act"
                elif _SECTION_WORD_BEFORE.search(text[max(0, start - 30) : start]):
                    # 3) "u/s 302" / "धारा 302" with no code named: use the code in force on the offence date.
                    code = default_code
                    source = "offence_date" if default_code else "unknown"
                else:
                    continue
        if code == "PROC":
            continue
        for item in _ITEM_RE.finditer(lst.group(0)):
            section = canonical_section(item.group(0))
            key = (section, code)
            if key in seen:
                continue
            seen.add(key)
            found.append(SectionRef(section, code, source, lst.group(0).strip()))
    return found


def _parse_dates(text: str) -> list[tuple[int, date, str]]:
    out: list[tuple[int, date, str]] = []
    for m in _NUMERIC_DATE_RE.finditer(text):  # Indian order: day/month/year
        d, mo, y = (int(g) for g in m.groups())
        try:
            out.append((m.start(), date(y, mo, d), m.group(0)))
        except ValueError:
            pass
    for m in _ISO_DATE_RE.finditer(text):
        y, mo, d = (int(g) for g in m.groups())
        try:
            out.append((m.start(), date(y, mo, d), m.group(0)))
        except ValueError:
            pass
    for m in _WORD_DATE_RE.finditer(text):
        month = _MONTHS.get(m.group(2).lower())
        if month:
            try:
                out.append((m.start(), date(int(m.group(3)), month, int(m.group(1))), m.group(0)))
            except ValueError:
                pass
    plausible = [(pos, d, t) for pos, d, t in out if 1950 <= d.year <= 2100]
    return sorted(plausible, key=lambda x: x[0])


def detect_dates(text: str) -> list[DateCandidate]:
    """Dates in the FIR, tagged by the nearest preceding label (occurrence / report)."""
    text = normalise_text(text)
    candidates: list[DateCandidate] = []
    for pos, value, raw in _parse_dates(text):
        context = text[max(0, pos - 90) : pos]
        occ = [m.end() for m in _OCCURRENCE_RE.finditer(context)]
        rep = [m.end() for m in _REPORT_RE.finditer(context)]
        if occ and (not rep or max(occ) > max(rep)):
            kind = "occurrence"
        elif rep:
            kind = "report"
        else:
            kind = "other"
        candidates.append(DateCandidate(value, raw, kind))
    return candidates


def code_for_date(offence_date: date) -> str:
    return "BNS" if offence_date >= BNS_COMMENCEMENT else "IPC"


def analyse_fir(text: str, offence_date: date | None = None) -> FirAnalysis:
    candidates = detect_dates(text)
    source = "provided"
    if offence_date is None:
        occurrence = [c for c in candidates if c.kind == "occurrence"]
        if occurrence:
            offence_date, source = occurrence[0].value, "occurrence"
        elif candidates:
            # An offence precedes its report, so the earliest date is the best unlabelled guess.
            offence_date, source = min(c.value for c in candidates), "earliest"
        else:
            source = "none"
    applicable = code_for_date(offence_date) if offence_date else None
    sections = detect_sections(text, default_code=applicable)

    warnings: list[str] = []
    if source == "earliest":
        warnings.append(
            "No date was labelled as the date of occurrence; the earliest date in the FIR was used. "
            "Enter the offence date if it is different."
        )
    if source == "none":
        warnings.append("No offence date was found. Enter it to decide between the IPC and the BNS.")
    codes = {s.code for s in sections if s.label_source == "explicit"}
    if applicable == "BNS" and "IPC" in codes:
        warnings.append(
            "The FIR cites IPC sections but the offence date is on or after 1 July 2024, when the BNS "
            "replaced the IPC. Check the offence date and the sections."
        )
    if applicable == "IPC" and "BNS" in codes:
        warnings.append(
            "The FIR cites BNS sections but the offence date is before 1 July 2024; offences committed "
            "before that date remain governed by the IPC. Check the offence date and the sections."
        )
    if any(s.label_source == "unknown" for s in sections):
        warnings.append("Some sections name no code and no offence date was found, so their code is unknown.")
    return FirAnalysis(sections, offence_date, source, candidates, applicable, warnings)


# ── reference table ──
@lru_cache(maxsize=1)
def load_offence_table() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def base_section(section: str) -> str:
    m = re.match(r"\d+[A-Z]?", section)
    return m.group(0) if m else section


def lookup_offence(code: str, section: str) -> tuple[str | None, dict | None]:
    """(matched key, entry) for a section of ``code``; tries the exact form, then the base section,
    then the first sub-section listed under that base. Returns (None, None) if not in the table."""
    table: dict = load_offence_table().get(code, {})
    if section in table:
        return section, table[section]
    base = base_section(section)
    if base in table:
        return base, table[base]
    for key, entry in table.items():
        if base_section(key) == base:
            return key, entry
    return None, None
