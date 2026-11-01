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


def render_report_email(
    report: DiagnosisReportV1 | PrescriptionReportV1,
    *,
    guidebook_link: str | None = None,
    guidebook_link_days: int = 7,
) -> tuple[str, str, str]:
    """Return (subject, text, html). `guidebook_link` adds the e-book download block."""
    if isinstance(report, DiagnosisReportV1):
        subject = "[SOSU] 릴스 진단서"
        sections = _sections_diagnosis(report)
    else:
        subject = "[SOSU] 릴스 처방전"
        sections = _sections_prescription(report)

    text_parts = [subject.removeprefix("[SOSU] "), ""]
    html_parts = [f"<h1>{escape(subject.removeprefix('[SOSU] '))}</h1>"]
    for title, raw_lines in sections:
        lines, evidence = _cite(raw_lines)
        text_parts.append(f"■ {title}")
        text_parts.extend(f"- {line}" for line in lines)
        if evidence:
            text_parts.append("  근거 질문")
            text_parts.extend(f"  {e}" for e in evidence)
        text_parts.append("")
        html_parts.append(f"<h2>{escape(title)}</h2><ul>")
        html_parts.extend(f"<li>{escape(line)}</li>" for line in lines)
        html_parts.append("</ul>")
        if evidence:
            html_parts.append(
                '<p style="color:#888;font-size:12px;margin:4px 0 0">근거 질문<br>'
                + "<br>".join(escape(e) for e in evidence)
                + "</p>"
            )
    if guidebook_link:
        note = GUIDEBOOK_NOTE.format(days=guidebook_link_days)
        text_parts += [f"■ {GUIDEBOOK_TITLE}", note, guidebook_link, ""]
        html_parts.append(
            f"<h2>{escape(GUIDEBOOK_TITLE)}</h2><p>{escape(note)}</p>"
            f'<p><a href="{escape(guidebook_link, quote=True)}" '
            'style="display:inline-block;padding:12px 20px;border-radius:999px;'
            'background:#c9bd94;color:#1b1f20;text-decoration:none;font-weight:600">'
            "가이드북 PDF 받기</a></p>"
        )
    text_parts.append(FOOTER)
    html_parts.append(f'<p style="color:#888">{escape(FOOTER)}</p>')
    return subject, "\n".join(text_parts), "\n".join(html_parts)
