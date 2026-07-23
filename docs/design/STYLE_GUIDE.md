# FE-003 톤앤매너 및 스타일 가이드

## 1. 제품 인상

브랜드 키워드: **차분한, 근거 중심의, 정돈된, 솔직한, 주도권을 주는**.

- “AI가 대신 만든다”보다 “내 경험을 함께 정리하고 검증한다”는 인상을 준다.
- 과장된 성공·합격 표현을 피하고, 정보 부족과 불확실성을 분명히 쓴다.
- 전문 도구의 밀도를 유지하되 사용자가 다음 행동을 한눈에 찾게 한다.

### 문체

- 짧은 능동문과 구체적인 동사: `경험 정리하기`, `근거 확인`, `확정 저장`.
- AI 결과: `AI가 정리한 초안입니다. 확인 후 저장하세요.`
- 근거 부족: `이 내용을 뒷받침할 원문 근거가 부족합니다.`
- 오류: 원인 요약 → 보존된 내용 → 다음 행동 순서.
- 금지: `완벽한`, `합격 보장`, `AI가 검증함`, 기술 오류 코드 단독 노출.

## 2. 색상 토큰

WCAG AA 대비를 구현 단계에서 실제 조합별 검증한다.

```css
:root {
  --color-bg: #F7F8FA;
  --color-surface: #FFFFFF;
  --color-surface-subtle: #F1F4F8;
  --color-border: #D8DEE8;
  --color-border-strong: #AAB4C3;
  --color-text: #172033;
  --color-text-muted: #5C667A;
  --color-text-subtle: #778195;

  --color-primary: #2856A3;
  --color-primary-hover: #1F478B;
  --color-primary-subtle: #EAF1FC;
  --color-focus: #1769E0;

  --color-ai: #6553B7;
  --color-ai-subtle: #F0EDFB;
  --color-confirmed: #167352;
  --color-confirmed-subtle: #E8F5EF;
  --color-evidence: #9A5A12;
  --color-evidence-subtle: #FFF3DF;

  --color-success: #167352;
  --color-warning: #9A5A12;
  --color-danger: #B42318;
  --color-info: #2856A3;
}
```

- Primary blue는 주요 행동·선택에만 사용한다.
- AI violet, confirmed green, evidence amber는 의미 토큰이며 장식용으로 섞지 않는다.
- 상태는 색 + 아이콘 + 텍스트를 함께 사용한다.

## 3. 타이포그래피

- 기본: `Pretendard, "Noto Sans KR", system-ui, sans-serif`.
- 숫자·ID는 동일 폰트의 tabular numbers. 긴 원문만 필요 시 `ui-monospace`를 보조 사용.

| 토큰 | 크기/행간 | 굵기 | 용도 |
|---|---:|---:|---|
| display | 32/42 | 700 | 빈 상태·온보딩 핵심 제목 |
| h1 | 24/34 | 700 | 페이지 제목 |
| h2 | 20/30 | 700 | 주요 섹션 |
| h3 | 16/24 | 650 | 카드·패널 제목 |
| body | 15/24 | 400 | 기본 본문·폼 |
| body-sm | 14/21 | 400 | 목록·보조 설명 |
| label | 13/18 | 600 | 필드·상태 label |
| caption | 12/18 | 500 | 메타데이터·출처 |

- 본문 읽기 폭 최대 72ch, 원문/자기소개서는 line-height 1.7.
- 제목은 2줄, 목록 제목은 1줄 ellipsis 후 tooltip/상세에서 전체 표시.

## 4. 공간·크기 토큰

- 4px base: `space-1 4`, `2 8`, `3 12`, `4 16`, `5 20`, `6 24`, `8 32`, `10 40`, `12 48`.
- 폼 필드 간 20px, 섹션 간 32px, 페이지 섹션 간 48px.
- 입력 높이 44px, button 40px(기본)/44px(주요), icon button 최소 40px.
- 카드 padding 20px; 밀집 목록 row 44px, 일반 목록 row 최소 56px.

## 5. 모서리·그림자·테두리

```css
--radius-sm: 6px;
--radius-md: 10px;
--radius-lg: 14px;
--shadow-popover: 0 8px 24px rgba(23,32,51,.12);
--shadow-modal: 0 20px 48px rgba(23,32,51,.18);
```

- 기본 카드: 1px border + surface, shadow 없음.
- hover 가능한 카드만 border 강도 변화; 떠 있는 menu/drawer/modal에만 shadow.
- pill은 상태·태그에만 사용하고 CTA를 pill 형태로 만들지 않는다.

## 6. 핵심 의미 표현

| 의미 | 시각 규칙 | 라벨 예시 |
|---|---|---|
| AI 초안 | violet 좌측 3px bar + sparkle outline 아이콘 + subtle 배경 | `AI 초안` |
| 사용자 확정 | green check-circle + 흰색/green subtle | `확정됨` |
| 원문 근거 | amber quote/file 아이콘 + underline 가능한 근거 번호 | `근거 2` |
| 부족 정보 | amber alert-triangle + 점선 테두리 | `정보 부족` |
| 오류 | red alert-circle + 오류 텍스트 | `확인 필요` |

- AI 콘텐츠를 italic으로만 구분하지 않는다.
- 근거 배지는 반드시 열기 동작을 제공하고 `aria-label="근거 2 열기"`처럼 명시한다.
- 사용자 편집 즉시 `AI 초안`을 제거하지 않는다. `수정됨·미확정`으로 전환하고 저장 후 `확정됨`이 된다.

## 7. 공고 매칭 상태

| 상태 | 색/아이콘 | 표시 문구 | 의미 |
|---|---|---|---|
| direct | green / check-circle | 직접 근거 | 요구사항을 명시적으로 뒷받침 |
| partial | blue / half-circle | 부분 근거 | 일부만 뒷받침 |
| indirect | gray / link | 간접 근거 | 해석이 필요한 연관성 |
| no_evidence | red / minus-circle | 등록된 근거 없음 | 저장 데이터에서 확인 불가 |
| needs_confirmation | amber / help-circle | 추가 확인 필요 | 사용자의 사실 확인 필요 |

- 상태 순서는 의미상 강도이며 성공률이 아니다. 퍼센트로 변환하지 않는다.
- badge 옆에 판단 이유 한 문장을 항상 제공한다.

## 8. 컴포넌트 상태

- Button: primary 1개/영역, secondary, ghost, danger. disabled opacity만 낮추지 말고 배경·테두리·텍스트 토큰 변경.
- Input: default/hover/focus/invalid/disabled/read-only. invalid는 red border + 연결된 설명.
- Card: default/hover/selected/AI/confirmed/warning. selected는 2px primary border + check.
- Tag: removable은 명확한 X 버튼, 키보드 삭제 가능. 역량 태그와 상태 badge를 시각적으로 구분.
- Toast: 성공 알림 4초, 오류는 사용자가 닫거나 문제 해결까지 유지. 중요한 오류는 작업 영역에도 남긴다.
- Skeleton: 실제 콘텐츠 형태와 유사, pulse는 1.5초 이상이며 `prefers-reduced-motion`에서 정지.

## 9. 아이콘·모션

- 아이콘: 단일 outline 세트(예: Lucide 또는 React Icons의 한 계열), 16/20/24px.
- 아이콘 단독 버튼은 tooltip과 accessible name 필수.
- 애니메이션: hover 120ms, panel/drawer 180–220ms ease-out, modal 160ms.
- AI 처리 중 과도한 shimmer 금지. 작은 spinner + 현재 단계 문구 사용.
- `prefers-reduced-motion`에서는 이동 전환 제거.

## 10. 접근성 검수 기준

- 일반 텍스트 대비 4.5:1, 큰 텍스트/UI 경계 3:1 이상.
- focus 표시를 hover와 다르게 하고 제거하지 않는다.
- 확대 200%에서 핵심 행동과 콘텐츠 손실 없음.
- 오류/처리/저장 상태는 live region으로 알리되 반복 알림을 피한다.
- accordion, tree, tabs, modal은 WAI-ARIA 패턴을 따른다.

## 11. 구현 체크리스트

자기소개서 수정 동작의 표시 라벨과 API 값은 다음처럼 고정한다.

| 사용자 라벨 | API `revision_type` |
|---|---|
| 짧게 | `shorten` |
| 구체적으로 | `expand` |
| 자연스럽게 | `natural` |
| 다시 작성 | `rewrite` |

- 모든 값은 CSS custom properties로 선언하고 컴포넌트에서 hex 직접 사용을 금지한다.
- `AI 초안/수정됨/확정됨/근거 부족` fixture를 Story 또는 mock 화면에서 확인한다.
- 1440, 1024, 768, 390px에서 패널 전환과 sticky 영역을 검증한다.
- light theme만 V1 범위이며 dark theme 토큰은 후속 작업이다.
- 브랜드 로고/일러스트보다 실제 데이터와 상태의 명료성을 먼저 구현한다.
