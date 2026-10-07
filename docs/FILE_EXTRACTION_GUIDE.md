# 파일 첨부·텍스트 추출 가이드

## 1. 지원 범위

채팅·경험·공고의 모든 파일 진입점은 `AttachmentService`를 사용하며 최대 10개를
선택할 수 있다. 파일당 25MiB, 요청 전체 100MiB가 기본 한도다.

| 종류 | 확장자 | 추출 방식 | 위치 정보 |
|---|---|---|---|
| 일반 텍스트 | `.txt`, `.md`, `.markdown` | 인코딩 판별 후 직접 읽기 | 줄 |
| PDF | `.pdf` | 페이지별 native text, 필요한 페이지만 OCR | 페이지·block |
| 이미지 | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.bmp`, `.tif`, `.tiff` | Tesseract OCR | 단어 box |
| Word Open XML | `.docx` | 문단·표 XML, 희소 문서의 이미지 OCR | 문단·표 |
| PowerPoint Open XML | `.pptx` | 실제 슬라이드 순서의 텍스트, 희소 슬라이드 이미지 OCR | 슬라이드 |
| 한글 Open XML | `.hwpx` | manifest/section XML | section·문단 |
| 레거시 Word·PowerPoint | `.doc`, `.ppt` | 격리 임시 폴더의 LibreOffice headless 변환 후 기존 파서 | 변환된 문단·표·슬라이드 |
| 레거시 한글 | `.hwp` | 한컴 HWP→HWPX 변환 후 HWPX 파서 | section·문단 |
| 음성 | `.wav`, `.mp3`, `.m4a`, `.ogg`, `.flac` | FFmpeg 정규화 후 OpenAI STT | 시작·종료 ms |
| 영상 | `.mp4`, `.mov`, `.webm`, `.mkv`, `.mpeg`, `.mpg` | FFmpeg로 audio track 분리 후 OpenAI STT | 시작·종료 ms |

레거시 형식과 미디어도 원본 저장까지는 항상 수행한다. 외부 변환기, FFmpeg,
API 키가 없는 환경에서는 임의로 내용을 추정하지 않고 `failed`와 정확한 capability
오류를 반환한다. 암호화 문서와 음성 track이 없는 영상은 지원하지 않는다.

클라이언트가 보낸 MIME만 신뢰하지 않는다. 서버는 확장자, 파일 시그니처,
ZIP 기반 문서의 내부 구조를 함께 확인하며 암호화·비정상 압축 문서를 거부한다.

## 2. 원본 보존과 처리 상태

유효한 파일은 텍스트 추출 전에 `LocalBlobStore`에 원본 바이트와 SHA-256 해시를
저장한다. DB에는 storage key와 메타데이터를 기록하고 신규 파일의 BLOB 필드는
비워 둔다. 파싱에 실패해도 원본을 삭제하지 않고 오류와 파서 버전을 남긴다.

```text
queued -> processing -> ready
                      -> partial
                      -> failed
                      -> unsupported
```

- `ready`: 본문 추출 완료
- `partial`: 일부 페이지 실패 또는 품질 점수가 기준보다 낮아 원본 확인 필요
- `failed`: 추출 실패. 원본과 `parse_error`는 보존
- `unsupported`: 시그니처나 형식 정책상 처리할 수 없음. 원본과 이유는 보존
- `POST /api/v2/attachments/{attachment_id}/process`: 저장된 원본 재처리

응답에는 `parser_version`, `quality_score`, `warnings`가 포함된다. 현재 파서 버전은
`career-file-parser-v2`다.

## 3. OCR 실행 환경

Python의 `pytesseract`는 OCR 엔진 자체가 아니라 Tesseract 실행기의 래퍼다.
Windows에는 Tesseract 5.x와 `kor`, `eng`, `osd` 언어 데이터를 별도로 설치해야
한다. 설치 뒤 다음 값을 필요에 따라 설정한다.

```dotenv
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
TESSDATA_PREFIX=C:\Program Files\Tesseract-OCR\tessdata
AI_OCR_TIMEOUT_SECONDS=60
AI_OCR_MIN_CONFIDENCE=0.65
AI_FILE_EXTRACTION_CONCURRENCY=2
```

`TESSERACT_CMD`가 비어 있으면 PATH와 Windows 기본 설치 경로를 순서대로 찾는다.
서버의 `GET /capabilities`에서 실행기 버전, 설치 언어와 누락 언어를 확인한다.
OCR이 준비되지 않은 환경에서는 native text 문서는 계속 처리하지만 이미지와
스캔 PDF 처리는 명확한 실패 상태를 반환한다.

2026-10-07 개발 PC 기준 Tesseract 5.4.0과 `kor`, `eng`, `osd`가 설치됐으며,
사용자 언어 데이터 경로 `C:\Users\mbc\AppData\Local\CareerMemory\tessdata`를
자동 탐지한다. 실제 한글 OCR smoke test도 통과했다. 다른 PC에서는 capability
검사 결과가 다를 수 있으므로 mock 통과만으로 실제 OCR 가능 여부를 판단하지 않는다.

## 4. OCR·PDF 처리 정책

- EXIF 방향, 투명 배경, 저조도 반전, 대비, 작은 이미지 확대를 전처리한다.
- OSD가 있으면 회전을 보정한다.
- 문서 자동·단일 block·희소 text 프로필을 순서대로 평가하고 품질이 좋은 결과를 쓴다.
- PDF는 native text block을 우선 사용하고 이미지 비중이 높거나 글자가 부족한
  페이지만 300 DPI OCR한다.
- 한 페이지의 OCR 실패가 다른 페이지의 native text를 버리지 않도록 격리한다.
- OCR 신뢰도가 기준보다 낮으면 `partial`과 warning으로 사용자 확인을 요구한다.

## 5. 채팅 입력 UX

`+` 파일 선택, `Ctrl+V` 붙여넣기, 드래그앤드롭은 같은 검증 파이프라인을 사용한다.
첨부 카드는 입력창 위에 가로로 나열되고 너비를 넘으면 가로 스크롤한다. 같은 파일의
중복 선택을 막고 최대 10개를 초과하면 즉시 안내한다. 선택 즉시 업로드하며 카드에
업로드·대기·추출·준비·부분 성공·실패·미지원 상태를 표시한다. 실패 카드의 `재시도`는
DB에 보존된 원본으로 새 작업을 만든다. 준비되지 않은 파일은 메시지 전송에 사용할
수 없다. 업로드와 서버 추출 동시성은 기본 2개로 제한한다.

## 6. 영속 작업 큐와 마이그레이션

`file_processing_jobs`는 작업 유형, 시도 횟수, lease, worker, 오류와 완료 시각을
저장한다. API는 빠른 응답을 위해 현재 요청 안에서 작업을 실행할 수 있지만 작업
레코드는 먼저 commit된다. 서버가 중단되면 만료된 lease를 다음 worker가 `queued`로
되돌려 이어서 처리한다. 최대 시도 횟수를 넘긴 작업은 무한 재시도하지 않는다.

```powershell
python -m AI_Engine.file_processing_worker --once
python -m AI_Engine.file_processing_worker --poll-seconds 2
python -m AI_Engine.migrate_attachment_blobs          # dry-run
python -m AI_Engine.migrate_attachment_blobs --apply  # 해시 검증 후 실제 이관
```

기존 DB BLOB은 additive migration 뒤에도 읽을 수 있다. `--apply`는 LocalBlobStore에
쓴 바이트의 SHA-256을 재검증한 레코드만 DB BLOB을 비우므로 중간 실패 시 원문을
파괴하지 않는다.

## 7. 외부 도구와 STT

| capability | 설정 | 현재 개발 PC |
|---|---|---|
| Tesseract | `TESSERACT_CMD`, `TESSDATA_PREFIX` | 5.4.0, kor+eng+osd 사용 가능 |
| LibreOffice | `LIBREOFFICE_CMD` | 미설치, DOC/PPT 변환 비활성 |
| 한컴 변환기 | `HWPX_CONVERTER_CMD` | 미설치, HWP 변환 비활성 |
| FFmpeg/FFprobe | `FFMPEG_CMD`, `FFPROBE_CMD` | 9.0 WinGet 설치본 자동 탐지 |
| STT | `OPENAI_API_KEY`, `AI_STT_MODEL` | `whisper-1` 타임스탬프 모드 구성 |

STT는 구간 타임스탬프를 원본 근거로 저장해야 하므로 현재 `whisper-1`의
`verbose_json` segment를 사용한다. 모델이 낸 텍스트만 저장하지 않고 provider,
model, start/end ms를 `transcription_segments`에 함께 기록한다. 정규화된 audio가
OpenAI 파일 API의 25MB 한도를 넘으면 자동 추정하지 않고 분할 필요 오류를 반환한다.

참고: [Tesseract 설치](https://tesseract-ocr.github.io/tessdoc/Installation.html),
[LibreOffice 명령행 변환](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html),
[HWPX 형식](https://tech.hancom.com/hwpxformat/),
[FFmpeg 문서](https://www.ffmpeg.org/documentation.html),
[OpenAI Speech to text](https://developers.openai.com/api/docs/guides/speech-to-text)

## 8. 검증

결정론적 fixture는 MD, native PDF, DOCX 표, PPTX 슬라이드 순서, HWPX 문단과
수치 보존을 검사한다. 실제 OCR은 한글 이미지와 설치된 `kor` 언어팩을 사용한다.

```powershell
python -m AI_Engine.benchmarks.evaluate_file_extraction
python -m AI_Engine.benchmarks.evaluate_attachment_pipeline
python -m pytest AI_Engine/tests -q
```

평가 지표는 required fragment recall, numeric token recall, character error rate,
OCR quality와 처리 시간이다. 결과는 `AI_Engine/benchmarks/RESULTS.md`에 기록한다.
