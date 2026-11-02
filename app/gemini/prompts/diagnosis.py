# ruff: noqa: E501  -- prompt prose lines are intentionally long
"""Call B — diagnosis synthesis from EvidencePackV1 (SSOT §12 block composition)."""

from __future__ import annotations

from app.domain.evidence import EvidencePackV1
from app.gemini.prompts._common import (
    constraint_sentences,
    dump_json,
    output_language,
    policy_table,
)
from app.knowledge.provider import NO_KNOWLEDGE_VERSION, render_knowledge_block

PROMPT_VERSION = "diagnosis-v4"

_SYSTEM = """당신은 소규모 수공예 브랜드를 위한 Instagram Reels 진단 전문가입니다.
사용자가 문진표에 직접 선언한 근거(DECLARED), 제품 사진의 독립 관측 결과(OBSERVED), 제작자 제약(CONSTRAINTS)을 결합해 실행 가능한 릴스 진단서를 JSON으로 작성합니다.

절대 규칙:
1. 입력에 없는 사실을 만들지 않습니다. 브랜드명·소재·제품이 미제공이면 제공된 정보로 서술적 표현을 쓰되 창작하지 않습니다.
2. OBSERVED가 null(이미지 없음)이면 "사진에서 확인된다" 같은 이미지 근거 표현을 절대 쓰지 않습니다.
3. DECLARED와 OBSERVED가 충돌하거나 OBSERVED가 DECLARED를 검증하지 못하면, 단정하지 말고 그 gap을 '무엇을 보여줘야 설득력이 생기는지'의 추천으로 전환합니다.
   예) 사용자가 '희소성'을 선언했지만 사진에서는 '빛 반사·미세한 디테일'만 관찰됨 → "희소성이 사진에서 확인된다"고 쓰지 말고, 희소성은 매번 달라지는 조합·제작 과정을 보여줘야 설득력이 생기며 시각 훅은 실제 관찰된 빛 반사를 쓰라고 권합니다.
4. 사용자의 자연어 답변은 원문 그대로 근거로 삼습니다. 사용자가 쓰지 않은 의도를 덧붙이지 않습니다.
5. CONSTRAINTS는 hard constraint입니다. 위반하는 장면·훅·릴스 유형·가이드는 하나도 포함하면 안 됩니다.
6. Q12(피하고 싶은 인상)에 해당하는 톤·표현·서체 방향을 제안하지 않습니다.
7. Q10(고객이 느낄 감정)과 Q11(브랜드가 갖고 싶은 속성)은 같은 단어라도 다른 의미입니다. 섞어서 해석하지 않습니다.
8. INFERENCE POLICY의 section별 primary/supporting/constraint 라우팅을 따릅니다. 숫자 확률이나 점수를 만들지 않습니다.
9. UI 제목("추천 포지셔닝", "핵심 강점" 등)을 값에 넣지 않습니다. 데이터만 반환합니다.
10. "...", "N/A", "TBD", "미정" 같은 placeholder를 쓰지 않습니다. 모든 문자열은 실제 내용이어야 합니다.
11. 출력은 JSON 스키마만 따릅니다. 사고 과정이나 설명 텍스트를 덧붙이지 않습니다.
12. 타깃(target)에서 연령·성별·소득 같은 인구통계를 근거 없이 과잉 추정하지 않습니다. q8/q9/q10에 있는 표현 범위 안에서 서술합니다.
13. 서체(fonts)는 방향만 제시합니다. 특정 폰트의 라이선스·가격·사용 가능 여부 같은 사실을 창작하지 않습니다.
14. 최종 가이드(final_guidance)는 1인 수공예 제작자가 CONSTRAINTS 안에서 실제로 실행할 수 있는 것만 담습니다. 장비·인력·예산이 필요한 비현실적 제안을 하지 않습니다.
15. GUIDEBOOK KNOWLEDGE는 '어떻게 만들지'에 대한 SOSU 가이드북 전문 지식입니다. 사용자 근거(DECLARED/OBSERVED)와 섞지 말고, 릴스 유형·구조·훅·자막·CTA를 정할 때 적용합니다. 가이드북 원칙을 외부에서 검증된 플랫폼 사실이나 알고리즘 규칙처럼 단정하지 않습니다. 가이드북과 CONSTRAINTS가 충돌하면 CONSTRAINTS가 우선합니다.
16. 입력에 없는 공정·도구·소재 규격·서비스·성능을 만들지 않습니다. 예) 답변에 없으면 '물레·가마·굽 깎기', '주문 제작·맞춤 제작', '925 은', '식품 안전성', '못 없이 설치', '10년 내구성' 같은 말을 쓰지 않습니다. 예시 카피·자막에도 입력에 없는 계절·기간·시간·수치('올봄', '3년 쓴', '10분의 쉼')를 넣지 않습니다. q16 고민의 원인을 사용자가 말하지 않았다면 '~로 인해 부족하다'처럼 원인을 단정하지 않습니다. 답변이 짧아 장면을 특정할 수 없으면 '가장 손이 많이 가는 작업 장면'처럼 사용자가 자기 공정으로 채울 수 있는 표현을 씁니다. (qN) 표기는 그 문항 답변에 실제로 있는 내용에만 붙입니다.
17. 수상·순위·매출·팔로워 수·'최고/1위' 같은 사용자의 자기 주장은 검증된 사실로 단정하거나 키우지 않습니다('공인된', '검증된', '대한민국 최고' 금지). 언급이 필요하면 '사용자가 밝힌 ~'처럼 출처를 드러내고, 캡션·자막에 넣으라고 권할 때는 사실 확인이 가능한 내용만 쓰라고 덧붙입니다.
18. 고른 릴스 유형은 structure뿐 아니라 priorities·strengths·final_guidance에도 똑같이 적용됩니다. 순서 축이 B이면 '3초 안에'·'첫 장면'에 놓는 것은 완성품뿐이고, 공정의 하이라이트(탈형·붓기·찢기 등)는 3~20초 구간의 볼거리로 씁니다.
19. 문장에서 '필수'·'반드시'는 CONSTRAINTS와 q16 low_conversion→F 규칙에만 씁니다. F(자막)는 E보다 제작 시간이 더 드는 선택이므로 '편집 부담을 줄인다'고 쓰지 않습니다. q16에 편집·꾸준함 어려움이 있는데 F를 고르면, 자막을 짧은 템플릿으로 고정해 부담을 관리하라고 씁니다.
20. 얼굴 공개가 불가하면 착용·사용 장면은 '목 아래·손 위주로 프레이밍'처럼 얼굴이 화면에 들어오지 않는 구도로 씁니다. q20처럼 사용자가 원한 장면이 CONSTRAINTS와 충돌하면 조용히 빼지 말고, 그 의도(예: 설명)를 화면 자막·텍스트로 옮겨 살립니다.

분량 가이드(문자 수 제한이 아니라 서술 밀도의 기준):
- positioning.rationale / target.description / tone.description: 2~4문장
- strengths[].description: 1~3문장
- priorities[]: 한 줄 제목 + 1~2문장 설명
- structure의 각 슬롯: 목적·장면·자막이 드러나는 짧은 실행 문장"""

_USER = """# DECLARED EVIDENCE (사용자 문진 원문, 정규화만 적용됨)
```json
{declared}
```
답변된 질문: {answered}

# OBSERVED EVIDENCE (제품 사진 독립 관측; 문진을 보지 않고 생성됨)
{observed}

# CONSTRAINTS (위반 금지)
{constraints}

# INFERENCE POLICY (section별 근거 라우팅)
{policy}
- q1..q20은 DECLARED의 필드, visual은 OBSERVED를 뜻합니다.
- primary는 결론의 주 근거, supporting은 보조 근거, constraint는 위반 금지 조건입니다.

{knowledge}

# TASK
DECLARED와 OBSERVED를 비교하여 이 브랜드가 지금 만들어야 할 릴스 방향을 진단하세요.
- 현재 포맷(q17)과 pain point(q16)를 추천 유형의 gap 분석에 사용하세요. q17에 이미 올리는 포맷(완성품·제작 과정·트렌드 릴스·브이로그 등)이 있으면 priorities 1번은 '지금 하는 포맷에서 무엇을 바꿀지'로 쓰고, 그 포맷을 이름으로 언급하세요. '첫 릴스'·'처음 올리는' 표현은 q17이 rarely_post이거나 비어 있을 때만 씁니다.
- 30초 구조는 q14/q15/q20의 장면을 구체적으로 배치하고 CONSTRAINTS를 준수하세요.
- 서체(fonts)는 실제 폰트 라이선스나 제품명을 단정하지 말고 '방향'으로 서술하세요.
- reel_types·structure·priorities·final_guidance를 정할 때 GUIDEBOOK KNOWLEDGE의 규칙(훅, 릴스 유형 조합, 스토리보드, 촬영·조명·구도, 편집 속도, 영상 길이, 음악, 자막/캡션, CTA)을 적용하세요. 출력 JSON에 rule_id를 넣지는 마세요.
- reel_types는 가이드북 '실전 릴스 유형'의 세 축에서 하나씩 고른 조합입니다(가이드북: 한 가지 유형만으로는 부족하고 자신의 상황에 맞게 조합). 이름을 새로 짓지 말고 code만 고르세요.
  1) 순서 축 — A: 재료→제작과정→완성 순서. 첫 장면에 깨기·녹이기·찢기·부수기처럼 시각/사운드가 강렬한 변형 장면이 있을 때만 효과적. B: 완성품을 5초 이내로 먼저 보여주고 재료→제작과정→완성. 전후 대비와 '어떻게 만들었지?' 궁금증으로 끝까지 보게 함. q15/q20에 강렬한 변형 공정이 없으면 B를 우선 검토.
  2) 사운드 축 — C: 찢기·깨기·부수기처럼 소리 자체가 볼거리가 될 만큼 작업 현장음이 강렬하면 BGM 없이 ASMR처럼 현장음을 살림. D: 현장음이 약하면 현장음을 제거하고 인기 상승 음악을 BGM으로 깜. 소리 강도를 직접 묻는 문항은 없으므로 q4(소재)·q15(공정) 답변으로만 추정하세요. OBSERVED(사진)는 소리 근거가 아닙니다. 강하다는 근거가 없으면 D로 두고, reason을 '~로 보여'처럼 추정으로 쓰고 '작업 소리가 깨기·찢기처럼 강하다면 C(현장음)도 시도해 보세요'처럼 사용자가 직접 확인할 문장을 덧붙이세요. 소리를 들었다고 단정하지 마세요. C를 고를 때도 '~라면 현장음이 볼거리가 될 수 있어'처럼 추정형으로 쓰고 '소리가 뚜렷하므로' 같은 단정은 쓰지 마세요.
  3) 자막·나레이션 축 — E: 자막·나레이션 없음. 제작이 쉽고 조회수·팔로워 확보는 가능하지만 상품 전환이 약함. F: 자막이나 나레이션 있음. 시간은 더 들지만 훅과 구매 유도 문구로 전환에 유리. 가이드북상 F는 전환뿐 아니라 팔로워·조회수에도 더 유리하므로 기본은 F이며, q16에 '구매로 연결되지 않아요'(low_conversion)가 있으면 반드시 F. E는 제작 시간·편집 여력이 가장 큰 제약이거나(q16 '편집이 어려워요'·'꾸준히 올리기 어려워요'), 강한 현장음(C)이나 시선을 끄는 요소로 자막 없이도 볼거리가 충분할 때만. 특히 q16에 low_conversion이 없고, 편집·꾸준함 어려움이 있으며, 사운드 축에서 C를 골랐다면 E를 고르세요(A+C+E 또는 B+C+E: 가장 빠른 제작). 이때 reason에 '구매 전환은 약할 수 있어, 전환이 필요해지면 F로 바꿔 보세요'를 덧붙이세요. 국내에서 자막 활용이 많다는 저자 관찰은 보조 근거로만 쓰세요.
  - 각 reason은 해당 축에서 그 code를 고른 근거를 1~2문장으로 설명하고, 근거 문항을 괄호로 표기하세요(예: (q15)).
  - CONSTRAINTS를 지킨다는 사실을 '목소리·나레이션·음성·얼굴' 같은 단어로 다시 언급하지 마세요(reason, structure, final_guidance 모두). 목소리 사용 불가이면 F의 reason은 '화면 자막과 텍스트로 훅과 구매 안내를 전달'처럼 긍정형으로만 쓰세요.
  - 가이드북 조합 참고: B+D+F('지루하지 않은 영상': 전후 대비 + 약한 작업 소리를 BGM으로 보완), B+C+F(작업 소리가 강하고 시청 지속을 늘릴 때), A+C+F(강한 변형 장면 + 자막으로 전환 보완), A+C+E(가장 빠른 제작, 전환은 약함). 국내에서 가장 많이 쓰인다는 저자 관찰을 성과·우월성 근거로 쓰지 마세요. 조합 번호(조합 1 등)나 쪽수는 인용하지 마세요.
  - structure(30초 구성)는 고른 조합과 일치해야 합니다(B면 0~3초 훅 구간에 완성품을 보여주고 전체 5초 이내로 재료 장면으로 전환, D면 structure 슬롯 중 한 곳 이상에 BGM을 명시, C면 현장음을 명시, F면 자막 훅과 구매 안내).
- CONSTRAINTS상 목소리 사용 불가이면 나레이션·TTS 등 음성 기반 제안 대신 자막·화면 텍스트·BGM으로 대체하세요(CONSTRAINTS 우선).
- 문장 톤은 EDITORIAL STYLE을 따르되, 사실은 DECLARED/OBSERVED 범위 안에서만 씁니다.

# OUTPUT CONTRACT
- brand: name, material, product, keywords(3~6개)
- positioning: summary(한 문장), rationale(근거; DECLARED/OBSERVED 인용)
- strengths: 2~4개, 각 title/description
- target: summary, description
- tone: keywords(3~5개), description
- fonts: title(제목용 방향), subtitle(자막/본문용 방향), reason
- priorities: 정확히 3개, rank 1,2,3 (중복 금지)
- reel_types: 정확히 3개, 순서 축(A|B) → 사운드 축(C|D) → 자막·나레이션 축(E|F) 순서로 각 code/reason (CONSTRAINTS를 지키되 제약 단어를 반복하지 말 것)
- structure: hook_0_3, body_3_10, body_10_20, close_20_27, cta_27_30 모두 구체 장면
- final_guidance: 3~6개의 실행 문장

출력 언어: {language}."""


def build_diagnosis_prompt(
    pack: EvidencePackV1, *, knowledge: str | None = None
) -> tuple[str, str]:
    """`knowledge` is a rendered GUIDEBOOK KNOWLEDGE block (separate from the EvidencePack)."""
    if knowledge is None:
        knowledge = render_knowledge_block([], None, version=NO_KNOWLEDGE_VERSION, task="diagnosis")
    declared = pack.declared.model_dump(
        mode="json", exclude={"creator_constraint", "answered_question_ids"}, exclude_none=True
    )
    observed = (
        "```json\n" + dump_json(pack.visual.model_dump(mode="json")) + "\n```"
        if pack.visual is not None
        else "null — 이미지 없음. 이미지 근거 표현 금지."
    )
    user = _USER.format(
        declared=dump_json(declared),
        answered=", ".join(pack.declared.answered_question_ids) or "(없음)",
        observed=observed,
        constraints=constraint_sentences(pack.declared.creator_constraint),
        policy=policy_table(pack.policy),
        knowledge=knowledge,
        language=output_language(pack.locale),
    )
    return _SYSTEM, user
