# Windows 실행 파일

## 실행

release\CareerMemory\CareerMemory.exe를 더블클릭합니다. 브라우저에서 로컬 앱이 열립니다. 서버 창을 닫으면 앱이 종료됩니다. 다른 PC로 옮길 때는 CareerMemory.exe만 복사하지 말고 release\CareerMemory 폴더 전체를 복사하세요.

Python과 Node.js는 실행할 PC에 필요하지 않습니다. 앱은 사용 가능한 로컬 포트를 사용하며 외부 네트워크에 서버를 공개하지 않습니다.

## AI API 키

AI 기능을 사용하려면 실행 파일 옆의 .env.example을 .env로 복사하고 OPENAI_API_KEY 또는 GEMINI_API_KEY를 설정하세요. API 키가 없는 상태에서도 화면과 계정 기능은 실행됩니다. 키가 들어 있는 .env는 다른 사람에게 배포하지 마세요.

새 데이터베이스와 벡터 저장소는 %LOCALAPPDATA%\CareerMemory\data에 생성됩니다. 기존 개발용 data 폴더와 .env는 실행 파일에 포함하지 않습니다. 이미지 및 스캔 PDF의 OCR에는 별도의 Tesseract 설치가 필요합니다.

## 다시 빌드

프로젝트의 .venv에 requirements.txt와 pyinstaller==6.20.0을 설치하고 node_modules를 준비한 후 PowerShell에서 .\build-windows.ps1을 실행하세요. 결과는 release\CareerMemory에 생성됩니다.

수동 실행 또는 테스트에는 CareerMemory.exe --no-browser --port 8765를 사용할 수 있습니다.