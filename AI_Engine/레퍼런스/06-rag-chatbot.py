# LLM이 사용자의 질문에 대한 답변을 바로하지 않고 PDF 문서에서 검색하여 대답할 수 있는 RAG[검색증강생성] 챗봇 만들기 -- 채팅 UI는 Gradio 모듈 이용.

# RAG 구현 워크폴로우(파이프라인) 설계
# 사용자 입력 --> 프롬프트 탬플릿 --> vector DB에서 검색(retrieval) --> LLM에게 답변 요청 --> 사용자

# 랭체인 RAG 구축 순서 -----------------------
# WORK #1. [구성요소1] 지식 검색기(리트리버)
#1. 지식이 될 PDF 문서 로드 --> 청크로 분할[pyPDFLoader, RecursiveCharacterTextSplitter]
#2. 벡터 DB 구축 [Chroma, OpenAIEmbeddings] ~ 파일로 저장
#3. 저장된 벡터 DB 가 있다면 불러와서 데이터를 검색해오는 검색기(리트리버)로 만들기 (vector_db.as_retriever)

# WORK #2. [구성요소2] 두뇌(모델)
#4. 질문에 답변 생성할 LLM 생성

# WORK #3. [구성요소3] 지침 및 사용자 입력(질문을 모델이 잘 수행하도록 하는 prompt)
#5. 프롬프트 탬플릿으로 프롬프트 정의 - 사용자 입력을 구조화

# WORK #4. 위 3개의 구성요소(runnable) [1]+[2]+[3] 체인 연결
# pip install langchain-classic
#6. 모델과 지침은 먼저 체인으로 연결 [2]+[3] ~ LCEL [model | prompt] ~ 최신: creaye_stuff_documents_chain()
#7. [1] 리트리버 + ([2][3])을 체인으로 연결 ~ create_retriever_chain()

# WORK #5. TEST
# 사용자 질문을 프롬프트 탬플릿 변수에 맞게 입력 {'input':'질문'}. invoke(), stream()

# WORK #6. [RAG AI 챗봇 UI 제작]
# pip install gradio
# grado 모듈로 UI 만들기
#-----------------------------------------
#=========================================
#-----------------------------------------

# WORK #1 [구성요소1] 검색기(리트리버)만들기
from langchain_community.document_loaders import PyPDFLoader
pdf_loader= PyPDFLoader('./프롬프트 엔지니어링/RAG 용 문서/2020_경제금융용어 700선_게시.pdf')
docs= pdf_loader.load()
print('문서 개수:', len(docs)) # PDF 문서에서 필요없는 페이지는 페이지를 제거하는 정제 작업 필요

from langchain_text_splitters import RecursiveCharacterTextSplitter
document_splitter= RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
chunks= document_splitter.split_documents(docs)
print('청크 개수:', len(chunks))

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv()

embeddings= OpenAIEmbeddings(model='text-embedding-ada-002')

# 벡터 db 영구적으로 저장하여 재사용하기 위해 저장 경로 미리 준비
import os
db_path= './05_langchain_rag/chrom_test_db_finacial.db'
if os.path.exists(db_path):
    #기존 벡터 있으면 DB 로드
    vector_db= Chroma(persist_directory=db_path, embedding_function=embeddings)
    print('기존 벡터 DB를 사용합니다')
else:
    #새로운 벡터DB 만들기 -- 이때 임베딩 비용 지불
    vector_db= Chroma.from_documents(chunks, embedding=embeddings, persist_directory=db_path)
    print('새 벡터 DB를 생성했습니다')

print('저장된 벡터값 문서(청크) 개수:',vector_db._collection.count())

# RAG 파이프라인의 구성요소로 등록되도록 검색기(리트리버)로 만들기
retriever= vector_db.as_retriever(search_kwargs={'k':3}) #유사도 높은 상위 3개 문서 검색

#-------------------------------------------------------------

# WORK #2. [구성요소2] 두뇌(모델)
from langchain_openai import ChatOpenAI
model= ChatOpenAI(model='gpt-4o-mini', temperature=0.1, max_completion_tokens=1000,)

#-------------------------------------------------------------

# WORK #3. [구성요소3] 지침 및 입력
from langchain_core.prompts import ChatPromptTemplate

# 프롬픝트 엔지니어링 기법 반영해 템플림 작성
# RAG에서 사용자 질문과 맥락을 프롬프트에서 인식하기 위해 정해놓은 변수명 -- {context}, {input} 사용
template= '''
[역할 role]
너는 한국 은행에서 만든 금융용어를 설명해주는 챗봇이야. 너는 함형준이 단독으로 개발했어.

[목표 task]
사용자의 질문에 대해 문맥으로 주어진 검색 결과를 바탕으로 답변해.

[문맥 context]
{context}

[제약조건 constraint]
- 검색결과에 없는 내용이면 답변할 수 없다고 해.
- 반말이지만 친절하게 대답해.
- 초등학생도 이해할 수 있게 설명해.

[형식 format]
- 설명 후에 주요 개념을 5개 이내로 개조식으로 요약해줘.
- 각 주요개념은 bullet 기호를 사용해.

질문: {input}
답변: 
'''

prompt= ChatPromptTemplate.from_template(template=template)

#-------------------------------------------------------------

# WORK #4. 위 3개의 구성요소를 체인으로 연결
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
model_prompt_chain= create_stuff_documents_chain(llm=model, prompt=prompt) # [2] + [3]
rag_chain= create_retrieval_chain(retriever, model_prompt_chain) #[1] + [2][3]

#-------------------------------------------------------------

# WORK #5. TEST -- 완료 후 주석 -- 돈 절약
# 사용자 질문을 프롬프트탬플릿으로 정의한 {'input':'질문'} 형식으로 invoke() or stream()

response= rag_chain.invoke({'input':'너는 무슨 챗봇이야?'})
print(response) # 메타 데이터 -- 근거 문서, 토큰량 등...
print('-'*30)

#챗봇 답변 출력
print(response['answer'].strip())
print('~'*30)

#-------------------------------------------------------------
# WORK #6. [RAG AI 챗봇 UI 제작] - gradio 모듈 사용'
import gradio as gr
with gr.Blocks() as demo:
    #마크다운으로 제목 표시
    gr.Markdown('# 금융용어가 어려우세요? 물어보세요!')

    # 필요 UI 구성요소 만들기(채팅창)
    chatbot= gr.Chatbot(label='MBCA AIX 경제금융용어 챗봇')
    input_box= gr.Textbox(label='질문해주세요')
    clear_button= gr.Button('대화 초기화')

    # [2] 아래 입력 박스에서 제출 버튼에 의해 실행될 함수 제작
    def get_response(input_question, chatbot_history): # llm 기억 말고 화면 기록(다시 그릴 때 위에 남겨두기 위함)
        # 위 WORK에서 만든 rag_chain 에게 사용자 질문을 입력하고 응답받기(글씨만)
        if input_question.strip() == '':
            return "", chatbot_history
        
        response= rag_chain.invoke({'input':input_question})
        response_answer= response['answer'].strip()

        #챗봇 대화 내역에 질문과 답변을 추가
        chatbot_history.append({'role':'user', 'content':input_question})
        chatbot_history.append({'role':'assistant', 'content':response_answer})

        #다음 입력을 편하게 하기 위해... input_box 요소에는 빈글씨를, chatbot 에게는 대화기록 리스트 리턴하기
        return "", chatbot_history

    # [1] 사용자 입력을 제출하면 실행될 함수 등록 및 파라미터로 전달할 값을 가진 요소 등록
    input_box.submit(
        get_response,
        [input_box, chatbot], # 요소를 주면... gradio가 알아서 그 안에있는 글씨를 파라미터로 가져감...
        [input_box, chatbot], # 3번째 파라미터 = 함수의 리턴값을 받을 요소들 등록
    ) 
    
    # [3] '대화 초기화' 버튼 누르면 모든 채팅 기록 삭제
    clear_button.click(lambda: [], None, chatbot, queue=False) # 명령들이 누적되어 늦게 실행되지 않도록 queue=False 하면 즉각 실행.

# gradio 웹앱 실행
demo.launch(debug=True) # http://127.0.0.1:7860