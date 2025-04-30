# src/project_aggregator/logic.py
import pathspec
from pathlib import Path
from typing import Optional, List, Set, Tuple
import sys
import os

# --- parse_gitignore 함수를 일반화 ---
def parse_ignore_file(root_dir: Path, ignore_filename: str) -> Optional[pathspec.PathSpec]:
    """
    지정된 ignore 파일을 파싱하여 pathspec 객체를 반환합니다.
    없거나 읽을 수 없으면 None을 반환합니다.
    """
    ignore_path = root_dir / ignore_filename
    spec = None
    if ignore_path.is_file():
        try:
            with open(ignore_path, 'r', encoding='utf-8') as f:
                # 파일 내용을 기반으로 pathspec 생성
                # .git은 load_combined_ignore_spec 에서 명시적으로 추가
                spec = pathspec.PathSpec.from_lines('gitwildmatch', f)
        except Exception as e:
            print(f"Warning: Could not read or parse {ignore_filename} at {ignore_path}: {e}", file=sys.stderr)
    return spec

# --- .gitignore와 .pagrignore를 함께 로드하는 함수 ---
def load_combined_ignore_spec(root_dir: Path) -> pathspec.PathSpec:
    """
    .gitignore와 .pagrignore 파일을 로드하고 규칙을 결합하여 최종 PathSpec 객체를 반환합니다.
    .git 디렉토리는 항상 무시 목록에 포함됩니다.
    """
    gitignore_spec = parse_ignore_file(root_dir, '.gitignore')
    pagrignore_spec = parse_ignore_file(root_dir, '.pagrignore')

    all_patterns = ['.git/'] # .git은 기본적으로 무시

    if gitignore_spec:
        all_patterns.extend(gitignore_spec.patterns)
        print(f"Info: Loaded rules from .gitignore", file=sys.stderr)
    if pagrignore_spec:
        all_patterns.extend(pagrignore_spec.patterns)
        print(f"Info: Loaded rules from .pagrignore", file=sys.stderr)

    # 여러 패턴 리스트를 결합하여 최종 PathSpec 생성
    # PathSpec.from_lines는 문자열 리스트나 반복 가능한 객체를 받음
    # PathSpec 객체 자체를 직접 합치는 API는 없으므로 패턴 리스트를 합쳐서 새로 만듭니다.
    combined_spec = pathspec.PathSpec.from_lines('gitwildmatch', all_patterns)
    return combined_spec


# --- Python 3.9+ (여기선 3.12+) 이므로 _is_relative_to 제거 ---
# def _is_relative_to(...): -> 제거

# --- generate_tree 함수는 그대로 두되, 인자로 받는 gitignore_spec 이름은 그대로 사용 ---
# 내부 로직에서 _is_relative_to 대신 path.is_relative_to 사용 (이미 되어 있을 수 있음)
def generate_tree(root_dir: Path, combined_ignore_spec: pathspec.PathSpec) -> str:
    """
    주어진 디렉토리의 트리 구조 문자열을 생성합니다.
    결합된 ignore 규칙(.gitignore + .pagrignore + .git)을 제외합니다.
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
        except FileNotFoundError: # 중간에 디렉토리가 사라지는 경우 등
            tree_lines.append(f"{prefix}└── [Error: Directory Not Found]")
            return


        # 필터링: ignore 규칙에 맞는지 확인
        filtered_items = []
        for item in items:
            # ignore 비교를 위해 root_dir 기준 상대 경로 사용
            # Path.is_relative_to 사용 (Python 3.9+)
            try:
                 if item.is_relative_to(root_dir):
                     relative_path = item.relative_to(root_dir)
                     # combined_ignore_spec 사용
                     if combined_ignore_spec and combined_ignore_spec.match_file(str(relative_path)):
                         continue # 무시 대상이면 건너뛰기
                     filtered_items.append(item)
                 else:
                     # 일반적으로 root_dir 내의 항목만 처리되므로 이 경고는 드물게 발생
                     print(f"Warning: Item {item} is not relative to root {root_dir}. Skipping.", file=sys.stderr)
            except ValueError: # is_relative_to가 False일 때 relative_to에서 발생 가능
                 print(f"Warning: Could not determine relative path for {item} against {root_dir}. Skipping.", file=sys.stderr)


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


# --- 지정된 디렉토리에서 파일을 스캔하고 필터링하는 함수 ---
def scan_and_filter_files(root_dir: Path, combined_ignore_spec: pathspec.PathSpec) -> List[Path]:
    """
    root_dir 아래의 모든 파일을 재귀적으로 찾고, combined_ignore_spec 규칙에 따라 필터링합니다.
    결과로 root_dir 기준 상대 경로 리스트를 반환합니다.
    """
    included_files: Set[Path] = set()
    # root_dir에서 시작하여 모든 하위 항목 순회
    for item in root_dir.rglob('*'):
        if item.is_file():
            try:
                # root 기준 상대 경로 계산
                if item.is_relative_to(root_dir):
                    relative_path = item.relative_to(root_dir)

                    # ignore 규칙 적용
                    if combined_ignore_spec and combined_ignore_spec.match_file(str(relative_path)):
                        # print(f"Debug: Ignoring {relative_path} due to rules.") # 디버깅 시 사용
                        continue # 무시 대상

                    # ignore 규칙에 걸리지 않으면 목록에 추가
                    included_files.add(relative_path)
                else:
                     print(f"Warning: Found file {item} not relative to root {root_dir}. Skipping.", file=sys.stderr)
            except ValueError:
                 print(f"Warning: Could not get relative path for {item}. Skipping.", file=sys.stderr)
            except Exception as e:
                 print(f"Error processing file {item}: {e}", file=sys.stderr)


    # 정렬된 리스트로 반환
    return sorted(list(included_files))


# --- aggregate_codes 함수는 거의 그대로 사용 ---
# 받는 인자 이름만 명확하게 relative_paths로 변경 (기존과 같음)
def aggregate_codes(root_dir: Path, relative_paths: List[Path]) -> str:
    """
    지정된 상대 경로 파일들의 내용을 읽어 하나의 문자열로 합칩니다.
    각 파일 내용 앞에는 파일 경로 헤더를 추가하고, 마크다운 코드 블록으로 감쌉니다.
    """
    aggregated_content = []
    separator = "\n\n" + "=" * 80 + "\n\n"

    for relative_path in relative_paths:
        header = f"--- File: {relative_path.as_posix()} ---"
        full_path = root_dir / relative_path
        formatted_block = ""

        try:
            # 여기서 full_path가 실제로 파일인지 한번 더 확인 (scan 결과이지만 안전하게)
            if not full_path.is_file():
                 print(f"Warning: Path {full_path} was not a file during aggregation. Skipping.", file=sys.stderr)
                 continue

            content = full_path.read_text(encoding='utf-8', errors='replace')
            suffix = relative_path.suffix.lower()
            language_hint = suffix[1:] if suffix else ""

            opening_fence = f"```{language_hint}"
            closing_fence = "```"
            formatted_block = f"{header}\n\n{opening_fence}\n{content}\n{closing_fence}"

        except FileNotFoundError:
             # scan 이후 파일이 삭제된 경우
             error_message = f"[Error: File disappeared since scanning: {full_path}]"
             formatted_block = f"{header}\n\n{error_message}"
             print(f"Error: File disappeared: {full_path}", file=sys.stderr)
        except PermissionError:
            error_message = f"[Error: Permission denied reading file: {full_path}]"
            formatted_block = f"{header}\n\n{error_message}"
            print(f"Error reading file {full_path}: Permission denied", file=sys.stderr)
        except Exception as e:
            error_message = f"[Error reading file: {e}]"
            formatted_block = f"{header}\n\n{error_message}"
            print(f"Error reading file {full_path}: {e}", file=sys.stderr)

        aggregated_content.append(formatted_block)

    # 각 파일의 포맷된 블록들을 최종 구분자로 합치기
    return separator.join(aggregated_content)