"""Server-side rendering of a VERIFIED report into a Korean e-mail. No client free text body."""

from __future__ import annotations

from html import escape

from app.contracts.diagnosis import DiagnosisReportV1
from app.contracts.prescription import PrescriptionReportV1

FOOTER = "본 메일은 SOSU에서 요청하신 리포트 사본입니다. 본인이 요청하지 않았다면 무시해 주세요."


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
        ("추천 릴스 유형", [f"{t.name}: {t.reason}" for t in r.reel_types]),
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
    for title, lines in sections:
        text_parts.append(f"■ {title}")
        text_parts.extend(f"- {line}" for line in lines)
        text_parts.append("")
        html_parts.append(f"<h2>{escape(title)}</h2><ul>")
        html_parts.extend(f"<li>{escape(line)}</li>" for line in lines)
        html_parts.append("</ul>")
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
