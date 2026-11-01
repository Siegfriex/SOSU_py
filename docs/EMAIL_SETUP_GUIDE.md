# 이메일 발송 켜기 — Gmail로 (도메인 없이)

이 가이드를 끝내면 사용자가 진단서·처방전 화면에서 **"메일로 받기"** 를 눌렀을 때 리포트와 **가이드북(전자책 PDF) 다운로드 버튼**이 메일로 갑니다. 버튼 링크는 7일 뒤 만료됩니다. 코드는 이미 배포되어 있고, 남은 일은 계정 설정과 환경변수 입력입니다.

- 발신: Gmail 계정 하나(SMTP + 앱 비밀번호). 도메인이 필요 없습니다.
- 한도: 개인 Gmail은 하루 약 500명 수신 — 수십 명 규모에는 충분합니다.
- Resend는 Resend에서 인증한 **유료 도메인**이 있어야 다른 사람에게 보낼 수 있습니다(is-a.dev 같은 무료 서브도메인은 거절됨). 나중에 도메인이 생기면 [아래](#나중에-resend로-바꾸기)처럼 바꿀 수 있습니다.

**진행 상황 확인:** 아무 때나 실행하세요. 메일은 보내지 않고 설정 상태만 봅니다.

```bash
cd SOSU_py && python3 scripts/check_email_setup.py
```

> ⚠️ 비밀번호·키는 **Vercel 화면과 내 컴퓨터의 `.env.local`에만** 넣으세요. 채팅·깃허브·메신저에 붙여 넣지 마세요.

## 1단계 — 발신용 Gmail 준비
1. 발신 전용 Gmail을 하나 정합니다(새로 만드는 것을 권장, 예: `sosu.report@gmail.com`). 받는 사람에게 이 주소가 보입니다.
2. 그 계정에서 <https://myaccount.google.com/security> → **2단계 인증** 을 켭니다.

## 2단계 — 앱 비밀번호 만들기
1. <https://myaccount.google.com/apppasswords> 에 들어갑니다(2단계 인증을 켜야 보입니다).
2. 앱 이름에 `sosu` 를 입력하고 **만들기** 를 누릅니다.
3. `abcd efgh ijkl mnop` 같은 16자리가 **한 번만** 표시됩니다. 바로 4단계에서 씁니다. 띄어쓰기는 넣어도 되고 빼도 됩니다.
   - 계정 비밀번호가 아니라 **이 앱 비밀번호**를 써야 합니다.
   - 계정 비밀번호를 바꾸면 앱 비밀번호가 무효가 되니 다시 만들어야 합니다.

## 3단계 — 가이드북 PDF를 Vercel Blob에 올리기
PDF는 **깃허브에 올리지 않습니다**(레포가 공개).
1. Vercel → **Storage** → **Create Database** → **Blob** → 이름 `sosu-guidebook`.
2. **Upload** 로 `가이드북 2차.pdf` 를 올리고, 파일 **URL을 복사**합니다(`https://….public.blob.vercel-storage.com/…pdf`).
   - 메일에는 이 URL이 직접 들어가지 않고, 7일 뒤 만료되는 서버 서명 링크(`/api/v1/guidebook?t=…`)가 들어갑니다.

## 4단계 — Vercel 환경변수 입력
서명 키를 먼저 만듭니다(64자리 출력, **한 번 정하면 바꾸지 마세요**):
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Vercel → **sosu-py** 프로젝트 → **Settings** → **Environment Variables** 에서 아래를 추가합니다. Environment는 **Production만**, 비밀값은 **Sensitive** 를 켭니다.

| Key | Value | Sensitive |
|---|---|---|
| `SOSU_SMTP_USERNAME` | 발신용 Gmail 주소 (예: `sosu.report@gmail.com`) | — |
| `SOSU_SMTP_PASSWORD` | 2단계의 앱 비밀번호 | ✅ |
| `SOSU_EMAIL_FROM` | `SOSU <sosu.report@gmail.com>` (꺾쇠 안은 위 Gmail 주소와 같게) | — |
| `SOSU_DELIVERY_SIGNING_SECRET` | 위에서 만든 64자리 값 | ✅ |
| `SOSU_GUIDEBOOK_URL` | 3단계의 Blob PDF URL | ✅ |
| `SOSU_PUBLIC_EMAIL_ENABLED` | `true` | — |

입력이 끝나면 **Deployments** → 맨 위 Production 배포의 **⋯** → **Redeploy**. **Redeploy를 해야 env가 반영됩니다.**

## 5단계 — 메일 남용 방지 규칙 (권장)
Vercel → **sosu-py** → **Firewall** → **Configure** → **New Rule**
- 이름: `SOSU email 5/10min/IP`
- If: **Request Path** equals `/api/v1/report-email` AND **Method** equals `POST`
- Then: **Rate Limit** → Fixed Window, 600초, 5 requests, Key: IP, Action: Too Many Requests(429)

**Review Changes** → **Publish**.

## 6단계 — 확인
1. `python3 scripts/check_email_setup.py` → 모두 ✅, 마지막 줄 🎉.
2. 운영 사이트(<https://sosu-rosy.vercel.app>)에서 진단 1건을 받고 **진단서 받기** → 본인이 아닌 주소(네이버·지인 Gmail 등)로 보냅니다.
3. 받은편지함과 **스팸함**, **가이드북 PDF 받기** 버튼이 열리는지 확인합니다.

## 문제 해결

| 증상 / 점검 결과 | 원인 | 해결 |
|---|---|---|
| ❌ `email_provider_not_configured` | `SOSU_SMTP_USERNAME`/`SOSU_SMTP_PASSWORD` 없음 또는 Redeploy 전 | 4단계 → Redeploy |
| ❌ `sender_not_configured` | `SOSU_EMAIL_FROM` 없음 | 4단계 |
| ❌ `signing_secret_not_configured` | 서명 키 없음 | 4단계 |
| ❌ `public_email_disabled` | 공개 스위치 꺼짐 | `SOSU_PUBLIC_EMAIL_ENABLED=true` → Redeploy |
| ❌ `guidebook_url_not_configured` | PDF URL 없음 | 3·4단계 |
| 화면에서 "메일 전송에 실패했어요" | 대부분 앱 비밀번호 오류(계정 비밀번호를 넣음, 2단계 인증 꺼짐, 비밀번호 변경으로 무효) | 앱 비밀번호를 새로 만들어 `SOSU_SMTP_PASSWORD` 교체 → Redeploy. Vercel 로그에서 `smtp auth failed` 확인 |
| 메일이 스팸함으로 감 | 새 Gmail 계정의 평판이 낮음 | 처음 몇 통은 받는 사람이 "스팸 아님"을 눌러 주면 개선됩니다 |
| 가이드북 버튼이 "링크가 만료되었어요" | 7일 지남 또는 서명 키 변경 | 리포트를 다시 받으면 새 링크가 옵니다 |

## 끄는 법
`SOSU_PUBLIC_EMAIL_ENABLED` 를 `false` 로 바꾸고 **Redeploy**. 화면은 "이메일 발송 기능은 준비 중" 으로 돌아가고 다른 기능에는 영향이 없습니다.

## 나중에 Resend로 바꾸기
Resend에서 인증한 도메인이 생기면 `RESEND_API_KEY` 를 넣고 `SOSU_EMAIL_FROM` 을 그 도메인 주소로 바꾼 뒤, `SOSU_SMTP_USERNAME`/`SOSU_SMTP_PASSWORD` 를 지우고 Redeploy 합니다. SMTP 값이 있으면 SMTP가 우선합니다.

## 참고 (기술)
- 메일 본문은 서버가 검증한 리포트로만 만듭니다. 사용자가 입력한 자유 텍스트는 본문에 들어가지 않습니다(`docs/EMAIL.md`).
- SMTP: `smtp.gmail.com:465`(암묵적 TLS). `SOSU_SMTP_HOST`/`SOSU_SMTP_PORT` 로 바꿀 수 있고, 587이면 STARTTLS를 씁니다. Gmail에는 Resend의 Idempotency-Key 같은 서버 측 중복 방지가 없어서, 같은 리포트·주소의 재발송 방지는 인스턴스 메모리 캐시(24시간)만 담당합니다.
- 가이드북 링크: `GET /api/v1/guidebook?t=<만료시각>.<HMAC>` → 유효하면 302로 `SOSU_GUIDEBOOK_URL`. 헤더 `Cache-Control: no-store`, `Referrer-Policy: no-referrer`. 유효 기간 `SOSU_GUIDEBOOK_LINK_MAX_AGE_SECONDS`(기본 7일).
