# src/project_aggregator/logic.py
import pathspec
from pathlib import Path
from typing import Optional, List, Set, Tuple
import sys
import os


# --- parse_ignore_file 함수는 그대로 둡니다 ---
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
                lines = f.readlines() # 라인별로 읽기
                 # 디버깅: 읽은 라인 출력 (앞뒤 공백 제거 후)
                read_lines = [line.strip() for line in lines if line.strip()]
                print(f"DEBUG: Lines read from {ignore_filename}: {read_lines}", file=sys.stderr)
                if not read_lines:
                     print(f"DEBUG: {ignore_filename} is empty or contains only whitespace.", file=sys.stderr)
                     return None # 빈 파일이면 spec 생성 안 함

                spec = pathspec.PathSpec.from_lines('gitwildmatch', read_lines) # 읽은 라인으로 spec 생성
                 # 디버깅: 생성된 spec의 패턴 출력 (정규식 형태로 나올 수 있음)
                if spec:
                    spec_patterns = [p.regex.pattern if p.regex else str(p) for p in spec.patterns]
                    print(f"DEBUG: Patterns parsed from {ignore_filename}: {spec_patterns}", file=sys.stderr)

        except Exception as e:
            print(f"Warning: Could not read or parse {ignore_filename} at {ignore_path}: {e}", file=sys.stderr)
    # else: # 파일이 없을 때 디버그 메시지 추가 (선택 사항)
    #    print(f"DEBUG: Ignore file not found: {ignore_path}", file=sys.stderr)
    return spec

# --- .gitignore와 .pagrignore를 함께 로드하는 함수 수정 (디버깅 강화) ---
def load_combined_ignore_spec(root_dir: Path) -> pathspec.PathSpec:
    """
    .gitignore와 .pagrignore 파일을 로드하고 규칙을 결합하여 최종 PathSpec 객체를 반환합니다.
    .git 디렉토리는 항상 무시 목록에 포함됩니다.
    """
    print(f"DEBUG: Loading ignore specs from root: {root_dir}", file=sys.stderr)
    gitignore_spec = parse_ignore_file(root_dir, '.gitignore')
    pagrignore_spec = parse_ignore_file(root_dir, '.pagrignore')

    # 각 spec 객체에서 실제 패턴 문자열 리스트를 추출합니다.
    # PathSpec 객체가 None일 경우 빈 리스트를 사용합니다.
    gitignore_patterns_str = []
    if gitignore_spec:
        gitignore_patterns_str = [p.pattern for p in gitignore_spec.patterns if hasattr(p, 'pattern')] # 패턴 문자열 추출
        print(f"DEBUG: Extracted patterns from gitignore_spec: {gitignore_patterns_str}", file=sys.stderr)

    pagrignore_patterns_str = []
    if pagrignore_spec:
        pagrignore_patterns_str = [p.pattern for p in pagrignore_spec.patterns if hasattr(p, 'pattern')] # 패턴 문자열 추출
        print(f"DEBUG: Extracted patterns from pagrignore_spec: {pagrignore_patterns_str}", file=sys.stderr)


    # 결합할 모든 패턴 문자열 리스트 생성 (.git/ 포함)
    all_pattern_strings = ['.git/']
    all_pattern_strings.extend(gitignore_patterns_str)
    all_pattern_strings.extend(pagrignore_patterns_str)

    print(f"DEBUG: All pattern strings being combined: {all_pattern_strings}", file=sys.stderr)

    # 결합된 문자열 리스트로부터 최종 PathSpec 객체 생성
    # 여기서 all_pattern_strings가 비어있으면 PathSpec([]) 와 같이 빈 Spec 객체가 생성됩니다.
    combined_spec = pathspec.PathSpec.from_lines('gitwildmatch', all_pattern_strings)

    # 최종 결합된 Spec 객체 내부의 패턴 확인 (정규식 패턴으로 보일 수 있음)
    final_patterns_repr = [p.regex.pattern if p.regex else str(p) for p in combined_spec.patterns]
    print(f"DEBUG: Final patterns in combined_spec object (regex form may appear): {final_patterns_repr}", file=sys.stderr)

    if not final_patterns_repr and (gitignore_spec or pagrignore_spec):
         print("DEBUG: Warning - Ignore files were found/parsed but final combined spec is empty. Check patterns.", file=sys.stderr)
    elif not final_patterns_repr:
         print("DEBUG: No ignore files found or parsed, final combined spec is empty (only default .git/ rule if any).", file=sys.stderr)


    return combined_spec

# --- Python 3.9+ (여기선 3.12+) 이므로 _is_relative_to 제거 ---
# def _is_relative_to(...): -> 제거

# --- generate_tree 함수 수정 (scan_and_filter_files와 유사하게 디버깅 추가) ---
def generate_tree(root_dir: Path, combined_ignore_spec: pathspec.PathSpec) -> str:
    """
    주어진 디렉토리의 트리 구조 문자열을 생성합니다.
    결합된 ignore 규칙(.gitignore + .pagrignore + .git)을 제외합니다.
    """
    tree_lines = [f"{root_dir.name}/"]
    print(f"DEBUG: Generating tree for {root_dir}...", file=sys.stderr)

    def _build_tree_recursive(current_dir: Path, prefix: str):
        try:
            items = sorted(list(current_dir.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
        except Exception as e:
            tree_lines.append(f"{prefix}└── [Error accessing directory: {e}]")
            return

        filtered_items = []
        for item in items:
            try:
                 if item.is_relative_to(root_dir):
                     relative_path = item.relative_to(root_dir)
                     relative_path_str = relative_path.as_posix() # POSIX 경로 문자열

                     # match_file 호출 및 결과 확인
                     should_ignore = combined_ignore_spec.match_file(relative_path_str) if combined_ignore_spec else False

                     # ===> 디버깅 핵심: 경로와 매치 결과 출력 <===
                     print(f"DEBUG: Tree Path='{relative_path_str}', Ignored={should_ignore}", file=sys.stderr)

                     if should_ignore:
                         continue # 무시 대상이면 건너뛰기
                     filtered_items.append(item)
                 else:
                     print(f"Warning: Item {item} is not relative to root {root_dir}. Skipping.", file=sys.stderr)
            except ValueError:
                 print(f"Warning: Could not determine relative path for {item} against {root_dir}. Skipping.", file=sys.stderr)
            except Exception as e:
                 print(f"Error processing tree item {item}: {e}", file=sys.stderr)

        pointers = ["├── "] * (len(filtered_items) - 1) + ["└── "]
        for pointer, item in zip(pointers, filtered_items):
            display_name = f"{item.name}{'/' if item.is_dir() else ''}"
            tree_lines.append(f"{prefix}{pointer}{display_name}")
            if item.is_dir():
                extension = "│   " if pointer == "├── " else "    "
                _build_tree_recursive(item, prefix + extension)

    _build_tree_recursive(root_dir, "")
    return "\n".join(tree_lines)


# --- scan_and_filter_files 함수 수정 (디버깅 강화) ---
def scan_and_filter_files(root_dir: Path, combined_ignore_spec: pathspec.PathSpec) -> List[Path]:
    """
    root_dir 아래의 모든 파일을 재귀적으로 찾고, combined_ignore_spec 규칙에 따라 필터링합니다.
    결과로 root_dir 기준 상대 경로 리스트를 반환합니다.
    """
    included_files: Set[Path] = set()
    print(f"DEBUG: Scanning files in {root_dir}...", file=sys.stderr)
    # combined_spec 내부 패턴 미리 확인 (위 load_combined_ignore_spec 에서 이미 출력됨)
    # final_patterns_repr = [p.regex.pattern if p.regex else str(p) for p in combined_ignore_spec.patterns]
    # print(f"DEBUG: Using combined spec with patterns: {final_patterns_repr}", file=sys.stderr)


    for item in root_dir.rglob('*'):
        if item.is_file():
            try:
                if item.is_relative_to(root_dir):
                    relative_path = item.relative_to(root_dir)
                    relative_path_str = relative_path.as_posix() # 비교할 POSIX 경로 문자열

                    # match_file 전에 비교 대상과 패턴 확인
                    # print(f"DEBUG: Checking file: '{relative_path_str}'", file=sys.stderr)

                    # match_file 호출 및 결과 확인
                    should_ignore = combined_ignore_spec.match_file(relative_path_str) if combined_ignore_spec else False

                    # ===> 디버깅 핵심: 경로와 매치 결과 출력 <===
                    print(f"DEBUG: Path='{relative_path_str}', Ignored={should_ignore}", file=sys.stderr)

                    if should_ignore:
                        continue # 무시 대상

                    included_files.add(relative_path)
                else:
                     print(f"Warning: Found file {item} not relative to root {root_dir}. Skipping.", file=sys.stderr)
            except ValueError:
                 print(f"Warning: Could not get relative path for {item}. Skipping.", file=sys.stderr)
            except Exception as e:
                 print(f"Error processing file {item}: {e}", file=sys.stderr)


    print(f"DEBUG: Found {len(included_files)} files after filtering.", file=sys.stderr)
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