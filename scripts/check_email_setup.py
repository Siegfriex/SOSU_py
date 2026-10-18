"""Report-email setup checker for the deployed API.

Read-only: one GET /api/v1/features, no e-mail is sent.

    python3 scripts/check_email_setup.py                       # https://sosu-py.vercel.app
    python3 scripts/check_email_setup.py https://my-api.example

Prints each step as ✅/❌ and, for the first missing step, exactly what to do next
(docs/EMAIL_SETUP_GUIDE.md has the full walkthrough). Exit 0 only when e-mail + guidebook are on.
"""

from __future__ import annotations

import json
import sys
import urllib.request

DEFAULT_API = "https://sosu-py.vercel.app"

# reason code from /features → (단계 이름, 해야 할 일). Order = order of the guide.
EMAIL_STEPS: list[tuple[str, str, str]] = [
    (
        "resend_not_configured",
        "① Resend API 키",
        "가이드 2~3단계: Resend에서 도메인을 인증하고 API 키를 만든 뒤, Vercel sosu-py → "
        "Settings → Environment Variables에 RESEND_API_KEY(Production, Sensitive)를 추가하세요.",
    ),
    (
        "sender_not_configured",
        "② 발신 주소",
        "가이드 5단계: SOSU_EMAIL_FROM = 'SOSU <report@인증한도메인>' 을 추가하세요. "
        "도메인은 Resend에서 Verified 상태여야 합니다.",
    ),
    (
        "signing_secret_not_configured",
        "③ 서명 키",
        '가이드 4단계: 터미널에서 python3 -c "import secrets;print(secrets.token_hex(32))" '
        "실행 결과를 SOSU_DELIVERY_SIGNING_SECRET(Sensitive)로 추가하세요.",
    ),
    (
        "public_email_disabled",
        "④ 공개 발송 스위치",
        "가이드 5단계: SOSU_PUBLIC_EMAIL_ENABLED = true 를 추가하고 Redeploy 하세요.",
    ),
]
GUIDEBOOK_STEPS = {
    "guidebook_url_not_configured": (
        "가이드 1단계: 가이드북 PDF를 Vercel Blob에 올리고 그 URL을 "
        "SOSU_GUIDEBOOK_URL(Sensitive)로 추가한 뒤 Redeploy 하세요."
    ),
    "signing_secret_not_configured": "③ 서명 키를 먼저 설정하세요(가이드 4단계).",
}


def main() -> int:
    api = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_API).rstrip("/")
    try:
        with urllib.request.urlopen(f"{api}/api/v1/features", timeout=15) as resp:
            features = json.load(resp)
    except Exception as exc:  # network / non-JSON: nothing else can be checked
        print(f"❌ {api}/api/v1/features 에 접속하지 못했습니다: {exc}")
        return 2

    print(f"SOSU 이메일 설정 점검 — {api} (build {features.get('build')})\n")
    email = features.get("email") or {}
    reason = email.get("reason")
    blocked_at = next((i for i, (code, _, _) in enumerate(EMAIL_STEPS) if code == reason), None)
    for i, (_, name, todo) in enumerate(EMAIL_STEPS):
        if email.get("enabled") or blocked_at is None or i < blocked_at:
            print(f"✅ {name}")
        elif i == blocked_at:
            print(f"❌ {name}\n   → 다음 할 일: {todo}")
        else:
            print(f"⏸  {name} (앞 단계 완료 후 확인)")
    if not email.get("enabled") and blocked_at is None:
        print(f"❌ 이메일 비활성 (알 수 없는 이유: {reason})")
        print("   → docs/EMAIL_SETUP_GUIDE.md 의 '문제 해결'을 확인하세요.")

    gb = features.get("guidebook")
    if gb is None:
        print("❌ ⑤ 가이드북 PDF 링크 — 이 배포는 가이드북 기능 이전 버전입니다.")
        print("   → 최신 커밋이 배포됐는지 확인하세요.")
        gb_ok = False
    elif gb.get("enabled"):
        print("✅ ⑤ 가이드북 PDF 링크")
        gb_ok = True
    else:
        todo = GUIDEBOOK_STEPS.get(gb.get("reason"), f"알 수 없는 이유: {gb.get('reason')}")
        print(f"❌ ⑤ 가이드북 PDF 링크\n   → 다음 할 일: {todo}")
        gb_ok = False

    if email.get("enabled") and gb_ok:
        print(
            "\n🎉 준비 완료. 운영 사이트에서 진단 1건 → '진단서 받기' → 본인 메일로 발송해 "
            "받은편지함(스팸함 포함)과 가이드북 링크를 확인하세요."
        )
        return 0
    print("\nenv를 바꾼 뒤에는 반드시 Deployments → 최신 Production → Redeploy 해야 반영됩니다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
