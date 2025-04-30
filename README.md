# pagr (Project Aggregator)

`pagr`는 프로젝트의 디렉토리 구조와 파일 내용을 하나의 텍스트 파일로 취합해주는 명령줄 도구입니다.
주로 ChatGPT와 같은 AI 모델에 프로젝트 컨텍스트를 쉽게 제공하기 위한 목적으로 만들어졌습니다.
`.gitignore`와 `.pagrignore` 파일을 통해 취합 대상에서 제외할 파일들을 지정할 수 있습니다.

## 설치

`pipx`를 사용하는 것을 권장합니다 (전역 환경에 영향을 주지 않고 CLI 도구를 설치/실행):

```bash
pipx install git+https://github.com/your-username/project_aggregator.git # 실제 저장소 주소로 변경하세요
# 또는 PyPI에 배포 후:
# pipx install project_aggregator
```

## 사용법

### 파일 취합 실행 (`run`)

```bash
# 현재 디렉토리를 대상으로 실행하고 결과를 Downloads/pagr_output.txt 에 저장 (기본값)
pagr run

# 특정 프로젝트 경로를 지정하고 결과를 현재 디렉토리의 output.md 에 저장
pagr run /path/to/your/project --output output.md
```

### 무시 규칙 편집 (`ignore`)

`pagr` 도구 자체의 무시 규칙을 담는 `.pagrignore` 파일을 편집합니다. Git으로 관리하지 않거나, AI 컨텍스트에 불필요한 파일(예: `*.lock`, `*.log`, `build/`, `dist/` 등)을 지정하기 좋습니다.

```bash
# 현재 디렉토리의 .pagrignore 파일을 기본 편집기로 엽니다 (없으면 생성).
pagr ignore
```
`.pagrignore` 파일의 형식은 `.gitignore`와 동일합니다.

### 기타 명령어

```bash
# 버전 확인
pagr --version

# 도움말 보기
pagr --help
pagr run --help
pagr ignore --help
```

## 개발

1. 저장소 클론: `git clone https://github.com/your-username/project_aggregator.git`
2. Poetry 설치: (설치되어 있지 않다면) `pip install poetry`
3. 의존성 설치: `cd project_aggregator && poetry install`
4. 가상환경에서 실행: `poetry run pagr --help`

 