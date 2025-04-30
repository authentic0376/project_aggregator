# pagr (Project Aggregator) 📄➡️📦

`pagr`는 프로젝트의 디렉토리 구조와 선택된 파일들의 내용을 하나의 텍스트 파일로 깔끔하게 취합해주는 명령줄 도구입니다. ChatGPT와 같은 AI 모델에게 프로젝트 전체 컨텍스트를 효율적으로 전달해야 할 때 유용하게 사용할 수 있습니다. `.gitignore` 파일과 추가적인 `.pagrignore` 파일을 통해 취합 대상에서 제외할 파일이나 디렉토리를 유연하게 관리할 수 있습니다.

## 🚀 설치 (Installation)

`pipx`를 사용하여 `pagr`를 설치하는 것을 강력히 권장합니다. `pipx`는 CLI 도구를 시스템의 다른 라이브러리와 격리된 환경에 설치하고 실행해주어, 파이썬 환경의 충돌을 방지합니다.

1.  **`pipx` 설치 (아직 없다면):**
    ```bash
    # pip를 통해 pipx 설치
    pip install --user pipx
    # PATH 환경변수에 pipx 경로 추가 (필요시)
    python -m pipx ensurepath
    ```
    (설치 후 터미널을 재시작해야 할 수도 있습니다. 자세한 내용은 [pipx 공식 문서](https://pypa.github.io/pipx/)를 참고하세요.)

2.  **`pagr` 설치 (via pipx):**
    ```bash
    pipx install project-aggregator
    ```
    이제 터미널 어디서든 `pagr` 명령어를 사용할 수 있습니다! 🎉

### 🤔 다른 설치 방법

*   **pip 사용 (가상환경 권장):**
    ```bash
    # 가상환경 생성 및 활성화 (예: venv)
    # python -m venv .venv
    # source .venv/bin/activate # Linux/macOS
    # .venv\Scripts\activate # Windows

    pip install project-aggregator
    ```
*   **최신 개발 버전 설치 (GitHub 직접):**
    ```bash
    pipx install git+https://github.com/authentic0376/project_aggregator.git
    ```

## 💡 사용법 (Usage)

### 🏃 파일 취합 실행 (`run`)

프로젝트 디렉토리 구조와 필터링된 파일 내용을 취합하여 하나의 파일로 만듭니다.

```bash
# 1. 현재 디렉토리를 대상으로 실행 (결과는 기본적으로 Downloads 폴더의 pagr_output.txt 에 저장)
pagr run

# 2. 특정 프로젝트 경로를 지정하고 결과를 현재 디렉토리의 output.md 에 저장
pagr run /path/to/your/project --output output.md

# 3. 도움말 보기
pagr run --help
```

### 🛠️ 무시 규칙 편집 (ignore)

`.gitignore` 외에 `pagr` 도구 자체의 무시 규칙을 담는 `.pagrignore` 파일을 편집합니다. 이 파일은 Git으로 관리할 필요가 없거나, AI 컨텍스트에 특히 불필요한 파일(예: `*.lock, *.log, build/, dist/`, 테스트 데이터 등)을 지정하기 좋습니다.

```bash
# 현재 디렉토리의 .pagrignore 파일을 기본 편집기로 엽니다 (파일이 없으면 새로 생성).
pagr ignore

# 도움말 보기
pagr ignore --help
```

`.pagrignore` 파일의 형식은 `.gitignore`와 동일합니다 (Git 와일드카드 패턴 사용).

### ℹ️ 기타 명령어
```bash
# 버전 확인
pagr --version

# 전체 도움말 보기
pagr --help
```