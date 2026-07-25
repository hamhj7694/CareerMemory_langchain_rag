#(실습1) 메모장 작성
from agents import function_tool
@function_tool
def open_notepad(response:str):
    '''Windows 메모장을 실행하고 사용자의 질문에 대한 답변을 파리미터 response로 받습니다.'''

    #메모장에 써질 글씨 확인
    print('AI응답 :', response)

    #1) 메모장 앱 실행
    import subprocess
    subprocess.Popen(r'C:\Users\mbc\AppData\Local\Microsoft\WindowsApps\notepad.exe')

    #2) 메모장 열리고 조금 대기 한 후 글 작성
    import time
    time.sleep(2)

    #3) 한글은 안됨.. 되게하려면 기능 만들어야 함.
    import pyperclip
    import pyautogui
    def slow_type_hangul(text, interval=0.25):
        for char in text:
            pyperclip.copy(char)         #한 글자씩 복사
            pyautogui.hotkey('ctrl','v') #붙여넣기
            time.sleep(interval)
    slow_type_hangul(response, interval=0.01)
    #----------------------------------------

    return "메모장을 실행했습니다."
#-----------------------------------------------------

#(실습2) 웹브라우저 열기
@function_tool
def open_webbrowser(url:str):
    '''웹브라우저를 엽니다. 전달받은 url 웹페이지를 열고 질문 받은 정보를 바탕으로 웹 검색을 진행합니다.'''
    import webbrowser
    webbrowser.open(url=url)
    return "웹 브라우저를 열었습니다."

#-----------------------------------------------------
# agent 만들기
from dotenv import load_dotenv
load_dotenv()
from agents import Agent, Runner
agent= Agent(
    name='RPA Agent',
    model='gpt-4o-mini',
    instructions='''
너는 사용자의 질문을 간경하게 대답하며, 사용자의 요청을 수행하는 에이턴트야.
open_notepad 함수를 사용한다면, 질문의 답변은 open_notepad 함수의 파라미터 response에 전달해줘.
open_webbrowser 함수를 사용한다면, 요청을 수행하기 위한 URL을 함수의 파라미터로 전달해줘.

작업 수행 내역을 bullet point를 사용해서 간단하게 정리하여 응답해줘.
''',
    tools=[open_notepad, open_webbrowser]
)

#(실습1)
# response= Runner.run_sync(agent, input='AI 개발자가 되기 위한 학습 방법을 간단하게 요약해서 메모장에 작성해줘.')
# print(response)

#(실습2)
# response= Runner.run_sync(agent,input='이번 주말에 일본 여행 갈거야. 항공권 정보 보여줘.')
response= Runner.run_sync(agent,input='오늘 저녁에 신림역 맛집을 검색하고 싶어. 네이버에서 검색해줘.')
print(response)