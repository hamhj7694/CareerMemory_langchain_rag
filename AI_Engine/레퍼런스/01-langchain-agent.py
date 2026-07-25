#랭체인 프레임워크 사용하여 openai, anthropic, google, Llama, 자체 LLM 등
#ai 모델들이 많음.. 회사별 Agent SDK를 추상화 하여 통일된 방식으로 에이전트 구현 가능

# 0. 설치
# pip install langchain langchain-openai

#1. api key load
from dotenv import load_dotenv
load_dotenv()

#2. 랭체인 LLM 모델 만들기
from langchain_openai import ChatOpenAI # from 랭체인_업체 import Chat모델
model= ChatOpenAI(model='gpt-4o-mini', temperature=0)

#3. 랭체인 Tools 연결
from langchain.tools import tool

@tool
def multiply(a:int, b:int)->int:
    '''두 숫자를 곱합니다.'''
    return a*b

#4. Agent 생성
from langchain.agents import create_agent
agent= create_agent(
    model=model, #이 모델을 위에서 다른 회사의 AI 회사의 LLM로 변경 가능 [모델 추상화]
    tools=[multiply]
)

#5. Agent 실행(사용자 질문)
# response= agent.invoke({
#     "messages":[{'role':'user', 'content':'123과 456을 곱해줘.'}]
# })
# print(response)
# print('-'*30)
# #마지막 AI의 응답 메시지만 출력
# print(response['messages'][-1].content)
# print()
#------------------

# 6. 여러개의 도구를 연결
@tool
def substract(a:int, b:int) -> int:
    '''두 숫자를 뺄셈합니다.'''
    return a-b

@tool
def weather(city:str)->str:
    '''도시의 날씨를 조회합니다.'''
    return f'{city}의 날짜는 맑음. 최고기온 31도, 최저기온 22도'

agent= create_agent(
    model=model,
    tools=[substract, multiply, weather]
)

#호출
# response=agent.invoke({
#     'messages':[
#         {'role':'user', 'content':'서울 날씨 알려주고, 가장 낮은 온도와 가장 높은 온도의 차이를 구해줘.'}
#     ]
# })
# print(response['messages'][-1].content)
# print('='*30)
# print()

#===============================
#7. 대화 메모리 사용
from langgraph.checkpoint.memory import InMemorySaver
memory= InMemorySaver()

agent= create_agent(
    model=model,
    tools=[substract, multiply, weather],
    checkpointer=memory
)

#대화기록 식별자를 langgraph 이전에는 session_id 라고 지칭했지만..
#지금 langgraph 에서는 thread_id 라고 지칭함.
#responses api의 previous의 경우에는 다른 사람의 대화기록도 저장 및 활용될 수 있지만.
#thread_id를 통해 대화구분이 용이해 짐.

config={
    "configurable":{
        "thread_id":'sam'
    }
}

# response= agent.invoke({
#     "messages":[
#         {'role':'user','content':'내 이름은 홍길동이야.'}
#     ]
# }, config=config)
# print(response['messages'][-1].content)

# response= agent.invoke({
#     "messages":[
#         {'role':'user','content':'내 이름이 뭐였지?'}
#     ]
# }, config=config)
# print(response['messages'][-1].content)

#8. 시스템 프롬프트 - 지침
agent= create_agent(
    model=model,
    tools=[substract, multiply],
    system_prompt='''
당신은 친절한 AI 비서입니다.
항상 한국어로 짧게 대답해요.
계산이 필요하면 Tool을 사용하세요.
'''
)

response=agent.invoke({
    'messages':[
        {'role':'user', 'content':'1970년 생은 지금 몇살이야?'}
    ]
})
print(response['messages'][-1].content)
print('-'*30)
print()
#-------------------------

#9. 토근단위로 스트리밍 : 실시간으로 글자가 생성되는 것처럼 출력되도록..타자 써지도록 하기
agent= create_agent(model=model, system_prompt='너는 강아지야 이름은 울이야.')
for token, metadata in agent.stream({"messages":[{'role':'user','content':'안녕'}]},stream_mode='messages'):
    print(token.content, end='', flush=True)