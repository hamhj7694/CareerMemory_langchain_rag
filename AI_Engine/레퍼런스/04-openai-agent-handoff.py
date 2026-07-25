# 여러 Agent를 조율하여 최종 목적을 달성하도록 하는 에이전틱 AI 개발에 용이한 기능

# 예제 : 수학 agent와 역사 Agent

from dotenv import load_dotenv
load_dotenv()

from agents import Agent, Runner

# 1) 수학 agent
math_agent= Agent(
    name='수학 선생님',
    model='gpt-mo-mini',
    instructions='수학 문제를 해결하는 전문가입니다.'
)

# 2) 역사 Agent
history_agent=Agent(
    name='역사 선생님',
    model='gpt-4o-mini',
    instructions='역사 질문에 답하는 전문가입니다.'
)

#문제해결에 적합한 agent를 조절하는 라우터 Agent 필요. (여러 Agent를 오케스트레이션하는 메인 Agent 필요)
router= Agent(
    name='감독 에이전트',
    model='gpt-4o-mini',
    instructions='''
    질문을 보고 적절한 전문가에게 전달하세요.
    만약, 두 전문가의 지식이 모두 필요하다면 한 에이전트의 결과를 다른 에이전트가 서로의 답변과 해설과 근거 내용 등을 공유해서 답변을 도출해 내도록 하세요.
    두 전문가의 지식이 아니라면 '모르는 분야 입니다. 저는 역사/수학 에이전트 입니다.' 라고 응답해.

    [제한사항]
    markdown 문법을 사용하지 말것.
    ''',
    handoffs=[math_agent, history_agent]
)

#(실습)
# result= Runner.run_sync(router, '세종대왕은 누구인가?') #역사
# print(result.final_output)
# print('-'*30)

# result= Runner.run_sync(router, '표준점수 구하는 방법은 뭐야?') #수학
# print(result.final_output)
# print('-'*30)

# result= Runner.run_sync(router, '조선이 건국된지 올해로 몇년이 되었는가?') #역사 + 수학
# print(result.final_output)
# print('-'*30)

# result= Runner.run_sync(router, '삼성전자 주식 지금 얼마야?') #주식 -- 모르는 분야
# print(result.final_output)
# print('-'*30)