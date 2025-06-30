# pagr (Project Aggregator) 📄➡️📦

`pagr`는 프로젝트의 디렉토리 구조와 선택된 파일들의 내용을 하나의 텍스트 파일로 깔끔하게 취합해주는 명령줄 도구입니다. ChatGPT와 같은 AI 모델에게 프로젝트 전체 컨텍스트를 효율적으로 전달해야 할 때 유용하게 사용할 수 있습니다.

- **`run` (기본 모드):** `.gitignore`와 `.pagrignore`에 명시된 파일을 **제외**하고 프로젝트를 취합합니다. (블랙리스트 방식)
- **`run-only` (지정 모드):** `.pagronly`에 명시된 파일**만**을 대상으로 취합합니다. (화이트리스트 방식)

## 🚀 설치 (Installation)

`pipx`를 사용하여 `pagr`를 설치하는 것을 강력히 권장합니다. `pipx`는 CLI 도구를 시스템의 다른 라이브러리와 격리된 환경에 설치하고 실행해주어, 파이썬 환경의 충돌을 방지합니다.

1.  **`pipx` 설치 (아직 없다면):**
    ```bash
    # pip를 통해 pipx 설치
    pip install --user pipx
    # PATH 환경변수에 pipx 경로 추가 (필요시)
    python -m pipx ensurepath
    ```
    (설치 후 터미널을 재시작해야 할 수도 있습니다.)

2.  **`pagr` 설치 (via pipx):**
    ```bash
    pipx install project-aggregator
    ```
    이제 터미널 어디서든 `pagr` 명령어를 사용할 수 있습니다! 🎉

## 💡 사용법 (Usage)

### 1. 지정 파일만 취합 (`run-only`)

`.pagronly` 파일에 명시된 패턴과 일치하는 파일들만 취합합니다. **특정 파일들만 골라 AI에게 전달하고 싶을 때 가장 추천하는 방식입니다.**

1.  **포함 규칙 정의 (`pagr only`):**
    ```bash
    # .pagronly 파일을 생성하고 편집기로 엽니다.
    pagr only
    ```
    열린 `.pagronly` 파일에 `src/`, `README.md` 와 같이 취합하고 싶은 파일/폴더 패턴을 추가하고 저장하세요.

2.  **`run-only` 실행:**
    ```bash
    # .pagronly 규칙에 따라 파일들을 취합합니다.
    pagr run-only

    # 결과를 특정 파일에 저장하고 싶다면:
    pagr run-only --output my_project.txt

    # 특정 루트 디렉토리를 기준으로 실행하고 싶다면:
    pagr run-only --root /path/to/project
    ```

### 2. 제외 방식으로 전체 취합 (`run`)

`.gitignore`와 `.pagrignore` 파일의 규칙을 제외한 모든 파일을 취합합니다. 프로젝트의 거의 모든 내용을 전달하고 싶을 때 사용합니다.

```bash
# 현재 디렉토리의 모든 파일(무시 규칙 제외) 취합
pagr run

# 결과를 특정 파일에 저장
pagr run --output full_project.txt
또한 run 명령어에 직접 파일/폴더 패턴을 인자로 전달하여 대상을 한정할 수도 있습니다.

# 'src' 폴더와 최상위의 모든 '.py' 파일만 대상으로 취합 (무시 규칙은 여전히 적용됨)
pagr run src "**/*.py"
```

### 3. 미리보기 (preview, preview-only)

파일을 실제로 생성하지 않고 어떤 파일들이 취합될지 목록을 미리 확인합니다.

```bash
# run-only 명령어가 어떤 파일을 포함할지 미리보기
pagr preview-only

# run 명령어가 어떤 파일을 포함할지 미리보기
pagr preview

# run 명령어에 패턴을 줬을 때의 결과 미리보기
pagr preview "src/**/*.py"
```

### 4. 설정 파일 편집
```bash
# 포함 규칙(.pagronly) 편집 (run-only 명령어용)
pagr only

# 무시 규칙(.pagrignore) 편집 (모든 명령어에 적용)
pagr ignore
```

### ℹ️ 기타 명령어
```bash
# 버전 확인
pagr --version

# 전체 도움말 보기
pagr --help

# 특정 명령어의 도움말 보기
pagr run-only --help
pagr run --help
```