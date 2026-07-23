# FE-003 디자인 레퍼런스 조사

- 조사일: 2026-07-22 (KST)
- 범위: AI 문서 편집, 근거 표시, 복잡한 정보 탐색, 커리어 경험·공고 매칭
- 원칙: 화면을 복제하지 않고 검증된 상호작용 원칙만 Career Memory RAG에 맞게 재구성한다.

## 비교 결과

| 관점 | 공식 출처 | 관찰한 패턴 | 적용 결정 | 복제하지 않는 요소 |
|---|---|---|---|---|
| AI 문서 편집 | [Notion AI 도움말](https://www.notion.com/help/notion-ai-faqs) | 선택 영역에 AI를 적용하고 결과를 수락·폐기·재시도할 수 있다. 페이지 문맥과 지정 소스를 함께 사용한다. | AI 결과를 즉시 확정하지 않고 `AI 초안` 상태로 표시한다. 자기소개서 AI 수정은 적용 전 비교/취소 경로를 둔다. | Notion의 블록 명령어, 브랜드 아이콘, 페이지 구조 |
| AI 기반 경력 작성 | [LinkedIn AI 작성 도우미](https://www.linkedin.com/help/linkedin/answer/a7147237) | 사용자가 먼저 내용을 입력한 뒤 AI 제안을 받고, 저장·건너뛰기·다른 안·원문 복귀를 선택한다. | 경험 구조화와 자기소개서에 `원문 보기`, `다시 생성`, `사용자 확정`을 명시한다. | 프로필 레이아웃, Premium 표시, 문구 |
| 커리어 정보 구조 | [LinkedIn 프로필 가이드](https://www.linkedin.com/help/linkedin/answer/a554351/how-do-i-create-a-good-linkedin-profile-?lang=en) | 경험·성과·역량을 섹션화하고, 첫 화면에서는 요약을 우선한다. | 경험은 `영역 > 프로젝트 > 경험` 계층, 상세는 요약→STAR/역할→역량→근거 순으로 둔다. | 공개 프로필/소셜 기능, 사진 중심 구성 |
| 공고 매칭 | [LinkedIn 직무 매칭 도움말](https://www.linkedin.com/help/linkedin/answer/a8078207) | 공고의 필수·우대 조건을 프로필/이력서와 비교해 등급과 짧은 설명을 제시한다. | 총점보다 요구사항별 근거 수준을 먼저 보여주고, 부족한 정보도 같은 비중으로 드러낸다. | 합격 가능성처럼 오해될 종합 점수, LinkedIn 등급 표현 |
| 근거 추적 | [ChatGPT Search 도움말](https://help.openai.com/en/articles/9237897-chatgpt-) | 답변 가까이에 인라인 인용을 두고, 전체 출처는 별도 패널로 확장한다. | AI 답변의 문장/단락에 근거 번호를 붙이고 우측 `근거 패널`에서 원문·파일·페이지를 확인한다. | 웹 검색 결과 카드, 퍼블리셔 로고 |
| Grounding 신뢰 | [Microsoft Copilot grounding 안내](https://support.microsoft.com/en-us/microsoft-365-copilot/what-information-does-copilot-use-to-answer-my-prompt) | 근거가 정확성을 높이지만 사용자의 출처 확인이 필요하며, 근거가 없을 수도 있음을 알린다. | 근거 없는 결과는 숨기지 않고 `근거 부족`으로 표시한다. 근거 배지는 클릭 가능한 검증 동작으로 만든다. | Copilot 브랜드 컬러·용어·채팅 외형 |
| 목록·상세 탐색 | [Linear Custom Views](https://linear.app/docs/custom-views), [Display options](https://linear.app/docs/display-options) | 고정 사이드바, 필터 가능한 목록, 우측 상세 패널, sticky 그룹 헤더로 맥락을 유지한다. | 데스크톱에서 경험 트리/주 작업/근거 패널의 3층 구조를 사용하되, 상세 집중 화면에서는 좌측을 축소한다. | 명령 팔레트, 이슈 상태 체계, 고밀도 테이블 외형 |
| AI 문서 개선 | [Atlassian Confluence AI 가이드](https://www.atlassian.com/software/confluence/resources/guides/best-practices/atlassian-ai) | 선택 텍스트를 요약·단축·톤 변경하고 결과를 검토한 뒤 문서에 추가한다. | 자기소개서 편집에서 `짧게`, `구체적으로`, `자연스럽게`, `다시 작성`을 선택 영역/전체 문서 범위와 함께 제공한다. | Confluence 툴바·슬래시 명령·Rovo 자산 |

## 채택한 방향

1. **검증 가능한 AI**: AI 결과 옆에서 근거를 열고, 근거 부족을 즉시 식별한다.
2. **사용자가 최종 편집자**: AI 출력은 초안이며 저장/확정 전 사용자가 편집한다.
3. **목록과 상세의 맥락 유지**: 경험 트리나 요구사항 목록을 유지한 채 상세를 탐색한다.
4. **점수보다 근거 수준**: 공고 매칭은 `직접·부분·간접·없음·확인 필요`를 요구사항 단위로 표현한다.
5. **집중도에 따른 밀도 조절**: 탐색 화면은 3패널, 작성 화면은 편집 영역을 넓히고 근거는 접을 수 있게 한다.

## 피할 방향

- AI를 보라색 그라데이션이나 반짝이 아이콘만으로 표현하지 않는다.
- 확률·합격 가능성으로 오해될 단일 종합 점수를 만들지 않는다.
- 상태를 색만으로 전달하지 않는다. 항상 텍스트·아이콘·형태를 병행한다.
- 원문과 AI 요약을 같은 카드 안에서 출처 표식 없이 섞지 않는다.
- 모바일에서 데스크톱 3패널을 축소해 우겨 넣지 않는다.

