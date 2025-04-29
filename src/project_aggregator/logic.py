# src/project_aggregator/logic.py
import pathspec
from pathlib import Path
from typing import Optional, List, Set
import sys

# --- parse_gitignore 함수는 그대로 둡니다 ---
def parse_gitignore(root_dir: Path) -> Optional[pathspec.PathSpec]:
    """
    .gitignore 파일을 파싱하여 pathspec 객체를 반환합니다.
    없거나 읽을 수 없으면 None을 반환합니다.
    """
    gitignore_path = root_dir / '.gitignore'
    spec = None
    if gitignore_path.is_file():
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                # gitignore 패턴과 함께 항상 무시할 .git 폴더 추가
                lines = f.readlines()
                lines.append('.git/') # .git 폴더는 항상 무시 목록에 추가
                spec = pathspec.PathSpec.from_lines('gitwildmatch', lines)
        except Exception as e:
            print(f"Warning: Could not read or parse .gitignore at {gitignore_path}: {e}", file=sys.stderr)
    else:
        # .gitignore 파일이 없어도 .git 폴더는 무시해야 함
         spec = pathspec.PathSpec.from_lines('gitwildmatch', ['.git/'])

    return spec

# --- _is_relative_to 함수는 그대로 둡니다 ---
def _is_relative_to(path: Path, base: Path) -> bool:
    """pathlib.Path.is_relative_to()의 Python 3.8 호환 버전"""
    if sys.version_info >= (3, 9):
        return path.is_relative_to(base)
    else:
        try:
            path.relative_to(base)
            return True
        except ValueError:
            return False

# --- generate_tree 함수는 그대로 둡니다 ---
def generate_tree(root_dir: Path, gitignore_spec: Optional[pathspec.PathSpec]) -> str:
    """
    주어진 디렉토리의 트리 구조 문자열을 생성합니다.
    pathspec 규칙 (및 .git)을 제외합니다.
    """
    tree_lines = [f"{root_dir.name}/"] # 최상위 루트 표시

    def _build_tree_recursive(current_dir: Path, prefix: str):
        """트리 구조를 재귀적으로 생성하는 내부 함수"""
        try:
            # 현재 디렉토리의 모든 항목을 가져와 정렬 (파일 우선, 이름순)
            items = sorted(list(current_dir.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            tree_lines.append(f"{prefix}└── [Error: Permission Denied]")
            return

        # 필터링: gitignore 규칙에 맞는지 확인
        filtered_items = []
        for item in items:
            # gitignore 비교를 위해 root_dir 기준 상대 경로 사용
            if _is_relative_to(item, root_dir):
                 relative_path = item.relative_to(root_dir)
                 if gitignore_spec and gitignore_spec.match_file(str(relative_path)):
                     continue # 무시 대상이면 건너뛰기
                 filtered_items.append(item)
            else:
                 print(f"Warning: Item {item} is not relative to root {root_dir}. Skipping.", file=sys.stderr)

        # 필터링된 항목으로 트리 라인 만들기
        pointers = ["├── "] * (len(filtered_items) - 1) + ["└── "]
        for pointer, item in zip(pointers, filtered_items):
            display_name = f"{item.name}{'/' if item.is_dir() else ''}"
            tree_lines.append(f"{prefix}{pointer}{display_name}")

            # 디렉토리면 재귀 호출
            if item.is_dir():
                extension = "│   " if pointer == "├── " else "    "
                _build_tree_recursive(item, prefix + extension)

    _build_tree_recursive(root_dir, "")
    return "\n".join(tree_lines)


# --- aggregate_codes 함수 수정 ---
def aggregate_codes(root_dir: Path, relative_code_paths: List[Path]) -> str:
    """
    지정된 파일들의 내용을 읽어 하나의 문자열로 합칩니다.
    각 파일 내용 앞에는 파일 경로 헤더를 추가하고,
    파일 내용은 마크다운 코드 블록(```)으로 감쌉니다.
    """
    aggregated_content = []
    # 파일 블록 사이의 구분자는 유지합니다.
    separator = "\n\n" + "=" * 80 + "\n\n"

    for relative_path in relative_code_paths:
        header = f"--- File: {relative_path.as_posix()} ---"
        full_path = root_dir / relative_path
        formatted_block = "" # 각 파일의 최종 포맷된 블록

        try:
            content = full_path.read_text(encoding='utf-8', errors='replace')

            # 파일 확장자를 기반으로 언어 힌트 생성 (선택 사항, 없으면 비워둠)
            suffix = relative_path.suffix.lower()
            language_hint = suffix[1:] if suffix else "" # 예: '.py' -> 'py'

            # 내용을 마크다운 코드 블록으로 감싸기
            # f-string 안에 백틱 3개를 넣으려면 ```{language_hint} 형태 사용
            opening_fence = f"```{language_hint}"
            closing_fence = "```"
            formatted_block = f"{header}\n\n{opening_fence}\n{content}\n{closing_fence}"

        except FileNotFoundError:
            # main에서 확인했지만, 만약을 대비한 에러 메시지
            error_message = f"[Error: File disappeared since validation: {full_path}]"
            formatted_block = f"{header}\n\n{error_message}"
            print(f"Error: File disappeared: {full_path}", file=sys.stderr)
        except Exception as e:
            # 다른 읽기 오류 처리 (예: 권한 문제, 인코딩 문제 심화)
            error_message = f"[Error reading file: {e}]"
            # 오류 메시지도 코드 블록으로 감쌀지, 그냥 둘지 선택 가능
            # 여기서는 그냥 둡니다.
            formatted_block = f"{header}\n\n{error_message}"
            print(f"Error reading file {full_path}: {e}", file=sys.stderr)

        aggregated_content.append(formatted_block)

    # 각 파일의 포맷된 블록들을 최종 구분자로 합치기
    return separator.join(aggregated_content)