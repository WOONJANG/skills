# Code Healing Factor

Codex에서 코드 결함을 재현하고, 원인을 찾아 수정한 뒤, 테스트 결과를 근거로 완료 여부를 판단하는 스킬입니다. 기존 동작을 먼저 확인하고 수정 후 관련 회귀 테스트를 다시 실행합니다.

## 설치 및 사용

검증 도구에는 **Python 3.11 이상**이 필요합니다. 이 저장소를 내려받고 `code-healing-factor` 폴더 전체를 설치 위치에 복사하세요.

| 범위 | 설치 위치 |
| --- | --- |
| 개인 (Windows) | `%USERPROFILE%\.agents\skills\code-healing-factor` |
| 개인 (Linux·macOS) | `~/.agents/skills/code-healing-factor` |
| 특정 프로젝트 | `<프로젝트>/.agents/skills/code-healing-factor` |

기존 설치본이 있으면 내용을 확인한 뒤 교체하세요. Codex에서 스킬이 보이지 않으면 Codex를 다시 시작하세요. [Codex 스킬 문서](https://learn.chatgpt.com/docs/build-skills)

프로젝트에서 Codex를 열고 다음처럼 요청하세요.

```text
$code-healing-factor 결제 금액이 0원일 때 발생하는 오류를 재현하고,
원인을 수정한 뒤 관련 회귀 테스트를 실행해 줘.
```

코드 검토만 원한다면 요청에 “파일은 수정하지 말고 재현과 진단만 해 줘”라고 명시하세요.

## 작동 방식

1. 프로젝트 규칙과 기존 테스트를 확인하고, 바뀌어야 할 동작과 보존할 동작을 구분합니다.
2. 실패를 재현하고 입력 경계, 예외 처리, 중복 요청 등 변경과 관련된 반례를 검토합니다.
3. 확인된 원인을 최소한의 변경으로 수정한 뒤 실패했던 테스트와 관련 회귀 테스트를 다시 실행합니다. 기본 수정 한도는 8회이며, 진전이 없는 시도가 2회 연속이면 접근을 바꿉니다.
4. 명령, 종료 코드, 소스 지문, 수정 이력을 JSON으로 기록합니다. Codex가 요구사항 충족 여부와 테스트의 타당성을 판단하고, Python 도구는 실행 결과와 필수 검증 항목을 집계합니다.

| 결과 | 의미 |
| --- | --- |
| `PASS` | 현재 소스의 필수 검증이 모두 통과했고 해결되지 않은 차단 결함이 없습니다. |
| `FAILED` | 실패한 검증 항목이나 해결되지 않은 차단 결함이 있습니다. |
| `BLOCKED` | 실행 환경, 권한, 시간 초과 또는 누락되거나 오래된 증거로 필수 검증을 마칠 수 없습니다. |

## 저장소 구성

- [SKILL.md](code-healing-factor/SKILL.md) — Codex가 읽는 스킬 정의와 실행 절차
- [heal.py](code-healing-factor/scripts/heal.py) — 검증 명령 실행, 소스 지문 생성, 수정 이력 및 결과 기록
- [검증 도구 사용법](code-healing-factor/references/runner.md) · [검증 계획 예제](code-healing-factor/references/plan.example.json)
- [검증 기준과 기술별 점검 항목](code-healing-factor/references/verification.md)
- [프로젝트 적용 및 선택형 Stop 훅 안내](code-healing-factor/references/activation.md)
- [자동 테스트](code-healing-factor/tests/test_heal.py)

## 테스트

저장소 루트에서 실행합니다. Windows에서는 `python` 대신 `py -3` 또는 Python 실행 파일의 전체 경로를 사용할 수 있습니다.

```powershell
python -B -m unittest discover -s code-healing-factor/tests -v
```

Windows에서 자동 테스트 11개를 통과했습니다. 별도 배송비 예제에서는 주문 금액이 정확히 50일 때의 오류를 재현하고 수정한 후, 49와 51에서도 기존 동작이 유지되는지 확인했습니다. 새 Codex 실행에서도 설치된 스킬을 명시적으로 호출해 경계값 및 회귀 테스트를 실행했습니다.

Stop 훅은 기본적으로 비활성 상태입니다. 모의 이벤트로 검증했으며, 실제 Codex 훅 실행과 자동 스킬 선택, Linux·macOS에서의 실행은 아직 확인하지 않았습니다.

검증 보고서와 수정 이력은 프로젝트 밖의 별도 작업 디렉터리에 저장하세요. 명령 인수와 검토 기록에는 자격 증명이나 개인정보를 넣지 마세요.

