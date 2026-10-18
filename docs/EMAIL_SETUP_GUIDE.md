# 이메일 발송 켜기 — 처음 하는 사람용 단계별 가이드

이 가이드를 끝내면 다음과 같이 동작합니다.
- 사용자가 진단서·처방전 화면에서 **"메일로 받기"** 를 누르면 리포트가 메일로 발송됩니다.
- 그 메일에 **가이드북(전자책 PDF) 다운로드 버튼**이 함께 들어갑니다. 버튼 링크는 7일 뒤 만료됩니다.
- 코드는 이미 배포되어 있습니다. 남은 일은 **계정 설정과 환경변수 입력**뿐입니다.

**진행 상황 확인:** 아무 때나 아래 명령을 실행하세요. 끝난 단계에는 ✅, 막힌 단계에는 ❌와 함께 **다음에 할 일**이 표시됩니다. 이 명령은 메일을 보내지 않습니다.

```bash
cd SOSU_py && python3 scripts/check_email_setup.py
```

| 필요한 것 | 비용 | 소요 |
|---|---|---|
| 내 도메인(예: `sosu.kr`) | 연 1~3만 원대 (없으면 구매) | 10분 |
| Resend 계정 (메일 발송 서비스) | 무료 플랜으로 시작 가능 (한도는 가입 화면에서 확인) | 10분 + DNS 반영 대기 |
| Vercel Blob (PDF 보관) | Pro 플랜 포함 사용량 내 | 5분 |

> ⚠️ 키·비밀값은 **Vercel 화면에만** 입력하세요. 채팅, 코드, 깃허브, 메신저에 붙여 넣으면 안 됩니다.

---

## 0단계 — 도메인 준비 (이미 있으면 건너뛰기)
Resend는 **내가 소유한 도메인**에서만 아무에게나 메일을 보낼 수 있습니다. `vercel.app` 주소로는 보낼 수 없습니다.

1. Vercel → 상단 **Domains** → **Buy** 에서 원하는 도메인을 검색해 구매합니다. 다른 곳(가비아 등)에서 사도 됩니다.
2. 메일 전용 하위 주소로 `send.내도메인` 같은 서브도메인을 쓰면 기존 홈페이지 설정과 충돌하지 않습니다. 0단계에서는 결정만 하면 됩니다.

## 1단계 — 가이드북 PDF를 비공개 보관소에 올리기
PDF는 **깃허브에 올리지 않습니다.** 레포가 공개이기 때문입니다.

1. Vercel → **Storage** → **Create Database** → **Blob** 을 선택하고 이름을 `sosu-guidebook` 으로 정해 만듭니다.
2. 만든 Blob 화면에서 **Upload** 로 `가이드북 2차.pdf` 를 올립니다.
   - 전자책용 다른 파일이 있다면 그 파일을 올려도 됩니다.
   - 18.7MB여도 괜찮습니다. 메일에 첨부하는 게 아니라 링크로 보내기 때문입니다.
3. 올린 파일의 **URL을 복사**해 둡니다(`https://….public.blob.vercel-storage.com/…pdf`). 5단계에서 씁니다.

> 이 URL은 무작위 문자열이 붙어 있어 추측하기 어렵지만, URL을 아는 사람은 누구나 받을 수 있습니다.
> 그래서 메일에는 이 URL을 **직접 넣지 않습니다.** 대신 우리 서버의 서명된 링크(`/api/v1/guidebook?t=…`)를 넣고, 링크가 7일 뒤 만료되면 더 이상 열리지 않습니다.
> 다만 사용자가 다운로드할 때 브라우저 주소창에는 Blob URL이 보입니다. 완전한 비공개(로그인 필요)를 원하면 별도 작업이 필요하니 요청해 주세요.

## 2단계 — Resend 가입과 도메인 인증
1. <https://resend.com> 에 가입합니다.
2. 왼쪽 **Domains** → **Add Domain** 을 누릅니다.
   - 0단계에서 정한 주소(예: `send.sosu.kr`)를 입력합니다.
   - Region은 가까운 곳(예: Tokyo)을 고릅니다.
3. 화면에 **DNS 레코드 3~4줄**(MX, TXT(SPF), TXT(DKIM) 등)이 나옵니다. 이 값을 도메인 DNS에 그대로 추가합니다.
   - **도메인을 Vercel에서 샀다면:** Vercel → Domains → 해당 도메인 → **DNS Records** → **Add** 에서, Resend 화면의 Type / Name / Value를 한 줄씩 복사해 넣습니다.
   - **다른 곳에서 샀다면:** 그 업체의 DNS 관리 화면에 같은 방식으로 넣습니다.
4. Resend로 돌아와 **Verify DNS Records** 를 누릅니다. 상태가 **Verified** 가 되면 완료입니다. 몇 분에서 길게는 몇 시간 걸릴 수 있습니다.

## 3단계 — Resend API 키 만들기
1. Resend → **API Keys** → **Create API Key** 를 누릅니다.
   - Name: `sosu-production`
   - Permission: **Sending access**
   - Domain: 2단계에서 인증한 도메인
2. `re_…` 로 시작하는 키가 **한 번만** 표시됩니다. 창을 닫지 말고 바로 5단계에서 Vercel에 붙여 넣으세요.

## 4단계 — 서명 키 만들기 (메일 링크 위조 방지용 비밀값)
터미널에서 아래 명령을 실행합니다. 64자리 영문·숫자가 출력됩니다.

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

출력된 값을 5단계에서 그대로 붙여 넣습니다. 이 값은 **한 번 정하면 바꾸지 마세요.** 바꾸면 이미 발급된 링크가 모두 무효가 됩니다.

## 5단계 — Vercel 환경변수 입력
Vercel → **sosu-py** 프로젝트 → **Settings** → **Environment Variables** 에서 아래 5개를 추가합니다.
- Environment는 모두 **Production만** 체크합니다.
- 비밀값 3개는 **Sensitive** 를 켭니다.

| Key | Value | Sensitive |
|---|---|---|
| `RESEND_API_KEY` | 3단계의 `re_…` 키 | ✅ |
| `SOSU_EMAIL_FROM` | `SOSU <report@send.sosu.kr>` (@ 뒤는 2단계에서 인증한 도메인) | — |
| `SOSU_DELIVERY_SIGNING_SECRET` | 4단계의 64자리 값 | ✅ |
| `SOSU_GUIDEBOOK_URL` | 1단계의 Blob PDF URL | ✅ |
| `SOSU_PUBLIC_EMAIL_ENABLED` | `true` | — |

입력이 끝나면 **Deployments** → 맨 위 Production 배포의 **⋯** → **Redeploy** 를 누릅니다. **Redeploy를 해야 env가 반영됩니다.**

## 6단계 — 메일 남용 방지 규칙 (권장)
Vercel → **sosu-py** → **Firewall** → **Configure** → **New Rule** 에서 아래처럼 만듭니다.
- 이름: `SOSU email 5/10min/IP`
- If: **Request Path** equals `/api/v1/report-email`, AND **Method** equals `POST`
- Then: **Rate Limit** → Fixed Window, 600초, 5 requests, Key: IP, Action: Too Many Requests(429)

마지막으로 **Review Changes** → **Publish** 를 누릅니다.

## 7단계 — 확인
1. `python3 scripts/check_email_setup.py` 를 실행해 모두 ✅ 인지 봅니다. 마지막 줄에 🎉 가 나오면 됩니다.
2. 운영 사이트(<https://sosu-rosy.vercel.app>)에서 진단을 1건 받습니다. 유료 호출 1건입니다.
3. **진단서 받기** 를 누르면, 입력칸 아래에 "가이드북(전자책 PDF) 다운로드 링크도 보내드려요" 문구가 보여야 합니다.
4. **본인 메일 주소**로 보내고 아래를 확인합니다.
   - 받은편지함과 **스팸함**
   - **가이드북 PDF 받기** 버튼을 누르면 PDF가 열리는지

## 문제 해결

| 증상 / 점검 결과 | 원인 | 해결 |
|---|---|---|
| ① ❌ `resend_not_configured` | `RESEND_API_KEY` 가 없거나 Redeploy 전 | 5단계 입력 → Redeploy |
| ② ❌ `sender_not_configured` | `SOSU_EMAIL_FROM` 없음 | 5단계 |
| ③ ❌ `signing_secret_not_configured` | 서명 키 없음 | 4~5단계 |
| ④ ❌ `public_email_disabled` | 공개 스위치 꺼짐 | `SOSU_PUBLIC_EMAIL_ENABLED=true` → Redeploy |
| ⑤ ❌ `guidebook_url_not_configured` | PDF URL 없음 | 1단계 → 5단계 |
| 화면에서 "메일 전송에 실패했어요" | Resend가 거절함. 주로 도메인 미인증 또는 발신 주소의 도메인 불일치 | Resend → **Logs** 에서 실패 이유를 확인합니다. `SOSU_EMAIL_FROM` 의 @ 뒤가 Verified 도메인인지 봅니다 |
| 메일이 스팸함으로 감 | 새 도메인의 평판이 낮음 | Resend 도메인 화면의 권장 DMARC 레코드를 추가합니다. 시간이 지나면 개선됩니다 |
| 가이드북 버튼이 "링크가 만료되었어요" | 7일이 지남. 또는 서명 키를 바꿈 | 리포트를 다시 받으면 새 링크가 옵니다 |
| 가이드북 버튼이 "준비 중이에요" | `SOSU_GUIDEBOOK_URL` 없음 | 1·5단계 → Redeploy |

## 끄는 법 (문제가 생기면)
`SOSU_PUBLIC_EMAIL_ENABLED` 를 `false` 로 바꾸고 **Redeploy** 하면 됩니다. 화면은 다시 "이메일 발송 기능은 준비 중" 으로 돌아가고, 다른 기능에는 영향이 없습니다.

## 참고 (기술)
- 메일 본문은 서버가 검증한 리포트로만 만듭니다. 사용자가 입력한 자유 텍스트는 본문에 들어가지 않습니다(`docs/EMAIL.md`).
- 가이드북 링크 형식은 `GET /api/v1/guidebook?t=<만료시각>.<HMAC>` 이고, 유효하면 302로 `SOSU_GUIDEBOOK_URL` 에 연결합니다.
  - 응답 헤더: `Cache-Control: no-store`, `Referrer-Policy: no-referrer`.
  - 유효 기간은 `SOSU_GUIDEBOOK_LINK_MAX_AGE_SECONDS` 로 정합니다(기본 604800 = 7일).
