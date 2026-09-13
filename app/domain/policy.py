"""Section 12 evidence routing. Single source of truth for the diagnosis prompt."""

from __future__ import annotations

from app.domain.evidence import InferencePolicyV1, SectionRouting

VISUAL = "visual"

INFERENCE_POLICY_V1 = InferencePolicyV1(
    routing={
        "positioning": SectionRouting(
            primary=["q2", "q3", "q5", "q6", "q7"],
            supporting=["q8", "q9", "q11", "q13", VISUAL],
            constraint=["q12"],
        ),
        "strengths": SectionRouting(
            primary=["q3", "q4", "q5", "q6", "q7", VISUAL],
            supporting=["q14", "q15"],
        ),
        "target": SectionRouting(
            primary=["q8", "q9", "q10"],
            supporting=["q2", "q3", "q11"],
        ),
        "tone": SectionRouting(
            primary=["q10", "q11", "q12", "q13"],
            supporting=["q9", VISUAL],
        ),
        "fonts": SectionRouting(
            primary=["q11", "q12", "q13"],
            supporting=["tone", VISUAL],
        ),
        "priorities": SectionRouting(
            primary=["q14", "q15", "q20", VISUAL],
            supporting=["q6", "q9"],
            constraint=["q18"],
        ),
        "reel_types": SectionRouting(
            primary=["q16", "q17", "q15"],
            supporting=["q6", "q9", "q14"],
            constraint=["q18"],
        ),
        "structure": SectionRouting(
            primary=["q14", "q15", "q17", "q20", VISUAL],
            supporting=["q6", "q9", "q16"],
            constraint=["q18"],
        ),
        "final_guidance": SectionRouting(
            primary=["q16", "q17", "q18"],
            supporting=["overall_synthesis"],
            constraint=["q18"],
        ),
    }
)
