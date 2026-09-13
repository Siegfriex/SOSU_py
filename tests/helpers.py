# ruff: noqa: E501
"""Shared sample payload builders (plain functions; also exposed as fixtures in conftest)."""

from __future__ import annotations

from typing import Any


def sample_answers_dict() -> dict[str, Any]:
    """모노유리 example (SSOT §6.1) expressed in CONTRACT V1 field names / codes."""
    return {
        "q1_brand_name": "모노유리",
        "q2_product_category": "유리 비즈로 만드는 키링과 작은 오브제",
        "q3_hero_product": "빛을 받으면 색이 달라 보이는 유리 키링",
        "q4_materials": "체코 유리비즈",
        "q5_material_reason": "빛에 따라 표정이 달라져서",
        "q6_product_appeals": ["design", "detail", "rarity"],
        "q7_differentiation": "같은 색 조합으로 대량 제작하지 않고 매번 조금씩 다르게 만듭니다.",
        "q8_target_customer": "흔한 캐릭터 제품보다 조금 독특한 소품을 좋아하는 20~30대",
        "q9_purchase_motives": ["aesthetic", "self_expression"],
        "q10_desired_emotions": ["excitement", "specialness"],
        "q11_brand_attributes": ["warmth", "specialness"],
        "q12_avoidance": "너무 유아적이거나 값싸 보이는 느낌",
        "q13_motif": "별빛, 물결",
        "q14_primary_message": "빛을 받았을 때 유리가 반짝이는 것",
        "q15_interesting_process": "색 조합을 고르고 하나씩 연결하는 과정",
        "q16_pain_points": ["low_reach", "ideation"],
        "q17_current_formats": ["finished_product"],
        "q18_disclosure": "face_only",
        "q20_must_show": "포장하기 전에 햇빛에 비춰보는 장면",
    }


def sample_diagnosis_request_dict() -> dict[str, Any]:
    return {"contract_version": "1.0", "locale": "ko-KR", "answers": sample_answers_dict()}


def sample_diagnosis_report_dict() -> dict[str, Any]:
    return {
        "schema_version": "diagnosis.v1",
        "brand": {
            "name": "모노유리",
            "material": "체코 유리비즈",
            "product": "빛에 따라 색이 달라 보이는 유리 키링",
            "keywords": ["빛", "유리 디테일", "개별성", "손맛"],
        },
        "positioning": {
            "summary": "빛에 따라 표정이 달라지는 작은 유리 오브제",
            "rationale": (
                "사용자는 디자인과 희소성을 강점으로 선언했고, 이미지에서는 유리 표면의 반사와 "
                "미세한 디테일이 가장 강한 시각 자산으로 관찰됩니다."
            ),
        },
        "strengths": [
            {
                "title": "빛에 반응하는 소재감",
                "description": "정적인 완성품보다 움직임 속에서 유리 반사가 드러날 때 차별점이 선명해집니다.",
            },
            {
                "title": "매번 다른 색 조합",
                "description": "대량 생산이 아닌 개별 조합이라는 점을 제작 과정으로 보여줄 때 희소성이 설득됩니다.",
            },
        ],
        "target": {
            "summary": "개별성이 있는 작은 오브제를 찾는 20~30대",
            "description": "예뻐서 사고, 나만의 것을 갖고 싶어 하는 고객에게 설렘과 특별함을 전달합니다.",
        },
        "tone": {
            "keywords": ["따뜻한", "섬세한", "조용한 특별함"],
            "description": "차분한 자연광, 느린 카메라 움직임, 과장 없는 자막으로 값싸 보이는 인상을 피합니다.",
        },
        "fonts": {
            "title": "단정한 산세리프, 중간 이상 굵기",
            "subtitle": "가독성 높은 산세리프 regular",
            "reason": "따뜻함과 특별함을 유지하면서 유아적이거나 값싸 보이는 인상을 피하기 위함입니다.",
        },
        "priorities": [
            {
                "rank": 1,
                "title": "햇빛을 통과하는 유리",
                "description": "첫 3초 안에 제품을 움직여 반사 변화를 보여줍니다.",
            },
            {
                "rank": 2,
                "title": "손으로 연결하는 과정",
                "description": "비즈를 고르고 하나씩 연결하는 손 클로즈업으로 개별 제작을 증명합니다.",
            },
            {
                "rank": 3,
                "title": "포장 전 마지막 점검",
                "description": "포장 전에 햇빛에 비춰보는 장면을 마무리 컷으로 씁니다.",
            },
        ],
        "reel_types": [
            {
                "name": "제작 디테일형",
                "reason": "현재 완성품 위주 콘텐츠에서 보이지 않던 제작 차별점을 보완합니다. 얼굴은 등장 가능하되 내레이션은 쓰지 않습니다.",
            },
            {
                "name": "빛 변화 무드형",
                "reason": "빛에 따른 색 변화라는 핵심 메시지를 자막만으로 전달합니다.",
            },
            {
                "name": "비포·애프터 조합형",
                "reason": "낱개 비즈에서 완성 키링까지의 변화로 아이디어 고갈 문제를 해결합니다.",
            },
        ],
        "structure": {
            "hook_0_3": "햇빛에 제품을 움직여 색 변화 노출",
            "body_3_10": "비즈 고르는 손 클로즈업",
            "body_10_20": "하나씩 연결되는 과정",
            "close_20_27": "완성품을 빛에 비춰보는 마지막 점검",
            "cta_27_30": "프로필 링크에서 이번 주 조합 확인 자막",
        },
        "final_guidance": [
            "매주 한 가지 색 조합을 정해 제작 과정 릴스를 먼저 올리세요.",
            "내레이션 대신 자막과 손동작으로 설명하세요.",
        ],
    }


def sample_prescription_request_dict() -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "locale": "ko-KR",
        "instagram_url": "https://www.instagram.com/reel/C0ffee123AB/",
    }


def sample_prescription_report_dict() -> dict[str, Any]:
    return {
        "schema_version": "prescription.v1",
        "prescription": {
            "summary": "도달은 있으나 저장·공유가 약해 초반 훅을 바꿔야 합니다.",
            "diagnosis": "스크린샷에서 조회수 대비 저장 수가 낮게 관찰되었고, 팔로워 외 도달 비율은 읽을 수 없어 추정하지 않았습니다.",
        },
        "next_actions": [
            {
                "order": 1,
                "title": "첫 1초 훅 교체",
                "description": "완성품 대신 빛 반사 장면으로 시작하세요.",
            },
            {
                "order": 2,
                "title": "자막 크기 확대",
                "description": "모바일에서 읽히도록 자막을 화면 폭 60% 이상으로 키우세요.",
            },
            {
                "order": 3,
                "title": "저장 유도 문구",
                "description": "마지막 3초에 '조합 저장해두기' 자막을 넣으세요.",
            },
            {
                "order": 4,
                "title": "게시 시간 고정",
                "description": "같은 요일·시간에 2주간 게시해 비교 데이터를 만드세요.",
            },
        ],
        "tone": {
            "keywords": ["차분한", "섬세한", "신뢰감"],
            "description": "빠른 컷 편집보다 느린 카메라 움직임과 자연광을 유지하세요.",
        },
    }
