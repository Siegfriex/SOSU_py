# Task mapping — 가이드북 규칙 → 리포트 섹션

키는 공개 응답 모델 필드명 그대로(`app/contracts/diagnosis.py::DiagnosisReportV1`, `app/contracts/prescription.py::PrescriptionReportV1`, `schema_version` 제외). `validate_pack.py`가 키 집합 == 모델 필드 집합을 검사한다.

## 규칙 선택 절차 (공통)
1. `applicability`에 해당 task가 포함된 규칙만 후보.
2. 섹션의 `task_mapping[task][section]` 카테고리로 필터.
3. 설문/관찰 신호를 `tags`와 매칭해 가중치. 태그는 **원시 코드**(`process`)와 **문항 접두 코드**(`q17_process`)를 모두 포함한다 — 충돌 코드(`process`는 q6·q17, `specialness`는 q9~q11, `yes/no`)는 접두형으로 매칭할 것.
4. `priority` 1 → 2 → 3 순. `author_experience`는 근거 보강용으로만, 단독 근거 금지.
5. `exceptions_or_cautions`가 있으면 문장에 반영(특히 불일치 라벨, 작가 주장).

## Diagnosis (설문 = 브랜드 속성 + 제품 시각 근거)
| 섹션 | 카테고리 | 주요 입력 → 규칙 예 |
|---|---|---|
| brand / positioning | brand_strategy, reels_fundamentals | q1–q8, q14 → "예쁨보다 구조"(FUND-005), 과정이 콘텐츠(FUND-001) |
| strengths | brand_strategy, ideation, lighting, reel_types | q6 `texture/detail` → 측면 조명(LIGHT-003/004), 접사(EQUIP-004); `material` → 유형 A 변형 장면(TYPE-002); `story` → 캡션 의미(CAP-004) |
| target | brand_strategy, caption, cta | q8, q9 `gift` → 구매/참여형 CTA(CTA-003, CTA-008) |
| tone | music_sound, lighting, editing_pacing, brand_strategy | q10/q11 → 브랜드 무드 음악(MUSIC-002), q12 회피 인상과 실수 공유 충돌 체크(IDEA-003) |
| fonts | composition, caption | 텍스트 안전 영역·위치(COMP-002/003). **가이드에 서체 추천 없음** → 서체 방향은 tone/q12 기반으로 쓰고 가이드 근거라고 주장하지 말 것 |
| priorities (3) | reels_fundamentals, combination, equipment, editing_pacing, cta, brand_strategy | q16/q17 → `rarely_post`면 바로 시작(BRAND-004, EQUIP-001); `low_conversion`→ F+구매 CTA(COMBO-003, CTA-005); `editing_difficulty`→ 무료 툴 최소 워크플로(EDIT-007) |
| reel_types (3) | reel_types, combination, music_sound | **첫 노출 우선순위**: 완성품 선공개(B) vs 재료 변형(A) 결정 → 작업 소리 강약(C/D) → 노출 가능 범위·목표(E/F). q18 `no/face_only`면 F는 자막/TTS로(BRAND-005, MUSIC-005) |
| structure (0–3/3–10/10–20/20–27/27–30초) | storyboard, hook, editing_pacing, video_length, cta, reel_types | 0–3초 훅+첫 요소(HOOK-001, TYPE-003 5초 이내), 본문 컷 ≤5초(EDIT-001), 재료·제작·제품 순서(STORY-002), 27–30초 CTA(CTA-001/005). 가이드 권장 길이는 30–60초(LEN-001) — 30초 템플릿은 하한값이라는 점을 인지 |
| final_guidance | equipment, lighting, composition, camera_angle, editing_pacing, caption, cta, ideation | 촬영 체크리스트(카메라 세팅, 45도 조명, 격자 중앙, 30–45도 각도), 캡션 3단 구조(CAP-002), 고정 댓글 CTA(CTA-004) |

## Prescription (인사이트 스크린샷 관찰 + 외부 근거)
| 섹션 | 카테고리 | 사용 방식 |
|---|---|---|
| prescription.summary / .diagnosis | performance_interpretation, reels_fundamentals, hook, editing_pacing, video_length | **관찰된 지표만** 인용 → 가이드 관점으로 *가설* 제시(PERF-001 첫 장면 궁금증, PERF-003 긴 컷, PERF-004 길이, PERF-005 훅) |
| next_actions (4) | performance_interpretation, hook, editing_pacing, video_length, caption, cta, combination, music_sound, ideation | 우선순위 = (관찰 근거 강도) × (rule priority). 각 액션은 **한 번에 한 변수만** 바꾸는 실험으로 기술(훅 유형 A/B, 컷 길이, CTA 유형, 자막 추가) |
| tone | music_sound, editing_pacing, brand_strategy | 유지/변경할 톤: BGM 무드, 템포(1.2–1.5배속), 꾸준함(PERF-008) |

### 처방 안전 규칙 (가이드 외 운영 원칙 — 규칙 팩에 GB 규칙으로 넣지 않음)
- 스크린샷에 없는 지표(전환, 저장, 유지율 등)는 **만들지 않는다**. "확인 불가"로 명시.
- 스크린샷은 상관 관찰일 뿐 **인과 증거가 아니다** → "~일 가능성", "~를 바꿔 비교해 보세요".
- 한 편의 결과로 결론 내리지 않는다(PERF-008).
- 외부 근거(플랫폼 문서 등)와 가이드 작가 주장이 충돌하면 둘 다 출처를 밝히고 단정하지 않는다.
- 가이드에는 인사이트 화면 해석 전용 장이 **없다**. performance_interpretation 규칙은 다른 장의 암묵적 내용에서 도출한 해석이다.
