"""Server-side rendering of a VERIFIED report into a Korean e-mail. No client free text body."""

from __future__ import annotations

import re
from html import escape

from app.contracts.diagnosis import DiagnosisReportV1
from app.contracts.prescription import PrescriptionReportV1
from app.domain.reel_types import code_of_name, combination

GUIDEBOOK_REEL_NOTE = "*릴스 유형은 가이드북 2장 '실전 릴스 유형' 참고"

# Survey question sentences (mirror of web/src/data/questions.ts labels, numbers/hints removed).
# The e-mail footnote shows the question only — never the user's answer (no client free text).
QUESTION_TEXT: dict[int, str] = {
    1: "브랜드 이름은 무엇인가요?",
    2: "어떤 제품을 만들고 있나요?",
    3: "가장 자신 있는 제품은 무엇인가요?",
    4: "주로 어떤 소재를 사용하나요?",
    5: "이 소재를 사용하는 이유는 무엇인가요?",
    6: "내 제품의 가장 큰 매력은 무엇인가요?",
    7: "비슷한 제품과 무엇이 다른가요?",
    8: "내 제품을 가장 좋아할 사람은 누구인가요?",
    9: "고객은 왜 이 제품을 사고 싶어 할까요?",
    10: "제품을 받은 고객이 어떤 기분을 느꼈으면 좋겠나요?",
    11: "우리 브랜드를 표현하는 단어는 무엇인가요?",
    12: "반대로, 이런 이미지는 피하고 싶다는 게 있나요?",
    13: "브랜드나 제품을 대표하는 상징이나 모티프가 있나요?",
    14: "제품에서 가장 어필하고 싶은 것은 무엇인가요?",
    15: "사람들이 보면 신기해할 만한 제작 과정이 있나요?",
    16: "지금 인스타그램에서 가장 어려운 점은 무엇인가요?",
    17: "지금 어떤 릴스를 주로 올리고 있나요?",
    18: "릴스에서 얼굴과 목소리를 공개할 수 있나요?",
    20: "릴스에서 꼭 보여주고 싶은 것이 있다면?",
}

# Same rules as web/src/data/evidence.ts: "(q4, q15)" groups are removed and collected;
# a bare "q17" becomes "17번 문항"; unknown numbers are left as written.
_GROUP_RE = re.compile(
    r"\s*[(（]\s*(?:문항\s*)?[qQ]\s*\d{1,2}(?:\s*[,，·/、]\s*(?:[qQ]\s*)?\d{1,2})*\s*[)）]"
)
_NUM_RE = re.compile(r"\d{1,2}")
_BARE_RE = re.compile(r"(?<![A-Za-z0-9])[qQ](\d{1,2})(?![0-9])")


def strip_refs(text: str) -> tuple[str, list[int]]:
    refs: list[int] = []

    def group(m: re.Match[str]) -> str:
        nums = [int(n) for n in _NUM_RE.findall(m.group(0)) if int(n) in QUESTION_TEXT]
        if not nums:
            return m.group(0)
        refs.extend(n for n in nums if n not in refs)
        return ""

    def bare(m: re.Match[str]) -> str:
        n = int(m.group(1))
        if n not in QUESTION_TEXT:
            return m.group(0)
        if n not in refs:
            refs.append(n)
        return f"{n}번 문항"

    return _BARE_RE.sub(bare, _GROUP_RE.sub(group, text)), refs


def _cite(lines: list[str]) -> tuple[list[str], list[str]]:
    """(lines without q-markers, footnote lines '15. 질문…' sorted by question number)."""
    out: list[str] = []
    refs: set[int] = set()
    for line in lines:
        text, found = strip_refs(line)
        out.append(text)
        refs.update(found)
    return out, [f"{n}. {QUESTION_TEXT[n]}" for n in sorted(refs)]


FOOTER = "본 메일은 SOSU에서 요청하신 리포트 사본입니다. 본인이 요청하지 않았다면 무시해 주세요."


def _reel_type_lines(r: DiagnosisReportV1) -> list[str]:
    lines = [f"{t.name}: {t.reason}" for t in r.reel_types]
    codes = [code_of_name(t.name) for t in r.reel_types]
    if all(codes):
        lines.insert(0, f"추천 조합: {combination([c for c in codes if c])}")
        lines.append(GUIDEBOOK_REEL_NOTE)
    return lines


def _sections_diagnosis(r: DiagnosisReportV1) -> list[tuple[str, list[str]]]:
    return [
        (
            "브랜드",
            [
                f"{r.brand.name} — {r.brand.product}",
                f"소재: {r.brand.material}",
                "키워드: " + ", ".join(r.brand.keywords),
            ],
        ),
        ("포지셔닝", [r.positioning.summary, r.positioning.rationale]),
        ("강점", [f"{s.title}: {s.description}" for s in r.strengths]),
        ("타깃", [r.target.summary, r.target.description]),
        ("톤앤매너", ["키워드: " + ", ".join(r.tone.keywords), r.tone.description]),
        ("서체", [f"제목: {r.fonts.title}", f"본문: {r.fonts.subtitle}", r.fonts.reason]),
        ("우선순위", [f"{p.rank}. {p.title}: {p.description}" for p in r.priorities]),
        ("추천 릴스 유형", _reel_type_lines(r)),
        (
            "30초 구성",
            [
                f"0~3초: {r.structure.hook_0_3}",
                f"3~10초: {r.structure.body_3_10}",
                f"10~20초: {r.structure.body_10_20}",
                f"20~27초: {r.structure.close_20_27}",
                f"27~30초: {r.structure.cta_27_30}",
            ],
        ),
        ("마무리 가이드", list(r.final_guidance)),
    ]


def _sections_prescription(r: PrescriptionReportV1) -> list[tuple[str, list[str]]]:
    return [
        ("처방 요약", [r.prescription.summary]),
        ("진단", [r.prescription.diagnosis]),
        ("다음 액션", [f"{a.order}. {a.title}: {a.description}" for a in r.next_actions]),
        ("톤", ["키워드: " + ", ".join(r.tone.keywords), r.tone.description]),
    ]


GUIDEBOOK_TITLE = "SOSU 릴스 가이드북 (전자책 PDF)"
GUIDEBOOK_NOTE = "아래 링크에서 가이드북 PDF를 내려받을 수 있어요. 링크는 {days}일 동안 유효합니다."
GUIDEBOOK_BUTTON = "가이드북 PDF 받기"
# From the guidebook's own cover copy (PDF p.1-3), quoted, not paraphrased into claims of ours.
GUIDEBOOK_TAGLINE = (
    "8개월 간 인스타그램 팔로워 29만 증가, 일일 최고점 조회수 1.7천만을 달성한 "
    "콘텐츠 PD의 수공예 특화 릴스 가이드"
)
SITE_URL = "https://sosu-rosy.vercel.app"
SPAM_NOTE = (
    "이 메일이 스팸함에 있었다면 '스팸 아님'으로 표시해 주세요. 다음 메일부터 받은편지함으로 와요."
)

# Guidebook chapters (PDF table of contents: 01 릴스의 이해 … 06 캡션) mapped to report sections.
_READING_DIAGNOSIS: list[tuple[str, str]] = [
    ("추천 릴스 유형", "2장 실전 릴스 유형: 순서·사운드·자막 유형과 나에게 맞는 조합"),
    ("30초 구성", "3장 콘텐츠 기획: 소재 발굴, 스토리보드 짜는 법"),
    ("30초 구성", "5장 편집: 컷 편집, 릴스 길이, 후킹 설계, 음악 선택"),
    ("마무리 가이드", "4장 촬영: 3만 5천 원 장비 리스트, 카메라 세팅, 빛·구도·각도"),
    ("자막·CTA", "6장 캡션: 캡션 구조, CTA, 캡션과 영상의 관계"),
]
_READING_PRESCRIPTION: list[tuple[str, str]] = [
    ("진단", "1장 릴스의 이해: 조회수가 잘 나오는 릴스와 안 나오는 릴스의 차이"),
    ("다음 액션", "5장 편집: 후킹 설계, 가장 효과적인 릴스 길이, 컷 편집"),
    ("다음 액션", "6장 캡션: 캡션 구조와 CTA"),
    ("다음 릴스", "2장 실전 릴스 유형: 나에게 맞는 유형 조합"),
]

_FONT = "-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif"
_BTN = (
    "display:inline-block;padding:12px 22px;border-radius:999px;background:#c9bd94;"
    "color:#1b1f20;text-decoration:none;font-weight:700"
)


def _clean(text: str) -> str:
    return strip_refs(text)[0].strip()


def _overview(report: DiagnosisReportV1 | PrescriptionReportV1) -> list[tuple[str, str]]:
    if isinstance(report, DiagnosisReportV1):
        rows = [("포지셔닝", _clean(report.positioning.summary))]
        codes = [code_of_name(t.name) for t in report.reel_types]
        if all(codes):
            rows.append(("추천 릴스 조합", combination([c for c in codes if c])))
        first = min(report.priorities, key=lambda p: p.rank)
        rows.append(("가장 먼저 보여줄 것", _clean(first.title)))
        rows.append(("첫 3초", _clean(report.structure.hook_0_3)))
        return rows
    first_action = min(report.next_actions, key=lambda a: a.order)
    return [
        ("처방 요약", _clean(report.prescription.summary)),
        ("다음 릴스에서 먼저 할 것", _clean(first_action.title)),
    ]


def _next_steps(report: DiagnosisReportV1 | PrescriptionReportV1, has_guidebook: bool) -> list[str]:
    if isinstance(report, DiagnosisReportV1):
        steps = [
            "진단서의 30초 구성대로 첫 릴스 1편을 찍어 올려 보세요.",
            f"올린 뒤 인사이트 캡처 3장으로 SOSU 처방전을 받아 보세요. {SITE_URL}",
        ]
        if has_guidebook:
            steps.insert(0, "가이드북 PDF를 내려받아 2장 '실전 릴스 유형'부터 읽어 보세요.")
        return steps
    steps = [
        "다음 액션 1번부터 다음 릴스에 하나씩 적용해 보세요.",
        f"다음 릴스를 올린 뒤 다시 처방전을 받아 변화를 비교해 보세요. {SITE_URL}",
    ]
    if has_guidebook:
        steps.insert(1, "가이드북 1장과 5장에서 훅과 편집 기준을 함께 확인해 보세요.")
    return steps


def render_report_email(
    report: DiagnosisReportV1 | PrescriptionReportV1,
    *,
    guidebook_link: str | None = None,
    guidebook_link_days: int = 7,
) -> tuple[str, str, str]:
    """Return (subject, text, html).

    Order: greeting → guidebook e-book block (first, when a link exists) with a reading guide that
    maps report sections to guidebook chapters → at-a-glance summary → full report sections with
    근거 질문 footnotes → next steps → footer. Only server-verified report data is used.
    """
    if isinstance(report, DiagnosisReportV1):
        doc = "릴스 진단서"
        brand = " ".join(report.brand.name.split())[:40]
        sections = _sections_diagnosis(report)
        reading = _READING_DIAGNOSIS
        greeting = f"{brand}의 {doc}가 도착했어요." if brand else f"요청하신 {doc}가 도착했어요."
        subject = f"[SOSU] {brand} {doc}" if brand else f"[SOSU] {doc}"
    else:
        doc = "릴스 처방전"
        sections = _sections_prescription(report)
        reading = _READING_PRESCRIPTION
        greeting = f"요청하신 {doc}이 도착했어요."
        subject = f"[SOSU] {doc}"
    overview = _overview(report)
    steps = _next_steps(report, guidebook_link is not None)

    t: list[str] = [doc, greeting, ""]
    h: list[str] = [
        f'<div style="max-width:600px;margin:0 auto;padding:8px 4px;font-family:{_FONT};'
        'color:#1b1f20;line-height:1.6;font-size:14px">',
        f'<h1 style="font-size:22px;margin:0 0 4px">{escape(doc)}</h1>',
        f'<p style="margin:0 0 20px;color:#444">{escape(greeting)}</p>',
    ]

    if guidebook_link:
        note = GUIDEBOOK_NOTE.format(days=guidebook_link_days)
        t += [f"■ {GUIDEBOOK_TITLE}", GUIDEBOOK_TAGLINE, note, guidebook_link, ""]
        t.append(
            "  이 진단 내용과 함께 보면 좋은 장" if doc == "릴스 진단서" else "  함께 보면 좋은 장"
        )
        t += [f"  - {sec} → {ch}" for sec, ch in reading]
        t.append("")
        link = escape(guidebook_link, quote=True)
        h += [
            '<div style="background:#f6f3ea;border-radius:12px;padding:20px;margin:0 0 24px">',
            f'<h2 style="font-size:16px;margin:0 0 6px">{escape(GUIDEBOOK_TITLE)}</h2>',
            '<p style="margin:0 0 8px;font-size:12px;color:#6b6250">'
            f"{escape(GUIDEBOOK_TAGLINE)}</p>",
            f'<p style="margin:0 0 14px">{escape(note)}</p>',
            f'<p style="margin:0 0 8px"><a href="{link}" style="{_BTN}">{GUIDEBOOK_BUTTON}</a></p>',
            '<p style="margin:0 0 16px;font-size:11px;color:#888;word-break:break-all">'
            "버튼이 열리지 않으면: "
            f'<a href="{link}" style="color:#888">{link}</a></p>',
            '<p style="margin:0 0 6px;font-weight:700;font-size:13px">'
            + ("이 진단 내용과 함께 보면 좋은 장" if doc == "릴스 진단서" else "함께 보면 좋은 장")
            + "</p>",
            '<ul style="margin:0;padding-left:18px;font-size:13px">',
            *(f"<li><strong>{escape(sec)}</strong> → {escape(ch)}</li>" for sec, ch in reading),
            "</ul></div>",
        ]

    t.append("■ 한눈에 보기")
    t += [f"- {k}: {v}" for k, v in overview]
    t.append("")
    h.append(
        '<div style="border:1px solid #e3ddcc;border-radius:12px;'
        'padding:16px 18px;margin:0 0 24px">'
        '<h2 style="font-size:16px;margin:0 0 8px">한눈에 보기</h2>'
    )
    h += [
        f'<p style="margin:0 0 6px"><strong>{escape(k)}</strong><br>{escape(v)}</p>'
        for k, v in overview
    ]
    h.append("</div>")

    for title, raw_lines in sections:
        lines, evidence = _cite(raw_lines)
        t.append(f"■ {title}")
        t.extend(f"- {line}" for line in lines)
        if evidence:
            t.append("  근거 질문")
            t.extend(f"  {e}" for e in evidence)
        t.append("")
        h.append(f'<h2 style="font-size:16px;margin:24px 0 6px">{escape(title)}</h2>')
        h.append('<ul style="margin:0;padding-left:18px">')
        h.extend(f'<li style="margin:0 0 4px">{escape(line)}</li>' for line in lines)
        h.append("</ul>")
        if evidence:
            h.append(
                '<p style="color:#888;font-size:12px;margin:6px 0 0">근거 질문<br>'
                + "<br>".join(escape(e) for e in evidence)
                + "</p>"
            )

    t.append("■ 다음 할 일")
    t += [f"{i}. {step}" for i, step in enumerate(steps, 1)]
    t += ["", SPAM_NOTE, FOOTER]
    h += [
        '<h2 style="font-size:16px;margin:28px 0 6px">다음 할 일</h2>',
        '<ol style="margin:0;padding-left:18px">',
        *(f'<li style="margin:0 0 4px">{escape(step)}</li>' for step in steps),
        "</ol>",
        '<hr style="border:none;border-top:1px solid #eee;margin:28px 0 12px">',
        f'<p style="color:#888;font-size:12px;margin:0 0 4px">{escape(SPAM_NOTE)}</p>',
        f'<p style="color:#888;font-size:12px;margin:0">{escape(FOOTER)}</p>',
        "</div>",
    ]
    return subject, "\n".join(t), "\n".join(h)
