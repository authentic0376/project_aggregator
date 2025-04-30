# src/project_aggregator/logic.py
import pathspec
from pathlib import Path
from typing import Optional, List, Set, Tuple
import sys
import os
import logging # 로깅 모듈 임포트

# 로거 인스턴스 가져오기 (logic 모듈용)
# __name__을 사용하면 로거 이름이 'project_aggregator.logic'이 됩니다.
logger = logging.getLogger(__name__)


# --- parse_ignore_file 함수 ---
def parse_ignore_file(root_dir: Path, ignore_filename: str) -> Optional[pathspec.PathSpec]:
    """
    지정된 ignore 파일을 파싱하여 pathspec 객체를 반환합니다.
    없거나 읽을 수 없으면 None을 반환합니다.
    """
    ignore_path = root_dir / ignore_filename
    spec = None
    logger.debug(f"Attempting to parse ignore file: {ignore_path}") # 함수 시작 로그

    if ignore_path.is_file():
        logger.debug(f"Found ignore file: {ignore_path}")
        try:
            with open(ignore_path, 'r', encoding='utf-8') as f:
                lines = f.readlines() # 라인별로 읽기
                 # 읽은 라인 처리 (앞뒤 공백 제거 후 비어있지 않은 라인만)
                read_lines = [line.strip() for line in lines if line.strip()]

                # DEBUG: 읽은 라인 로깅 (내용이 길 수 있으므로 주의)
                # logger.debug(f"Raw lines read from {ignore_filename}: {lines}")
                logger.debug(f"Stripped non-empty lines from {ignore_filename}: {read_lines}")

                if not read_lines:
                     logger.debug(f"{ignore_filename} is empty or contains only whitespace after stripping. No patterns to parse.")
                     return None # 빈 파일이면 spec 생성 안 함

                # PathSpec 객체 생성
                spec = pathspec.PathSpec.from_lines('gitwildmatch', read_lines)

                # DEBUG: 생성된 spec의 패턴 로깅 (정규식 형태로 나올 수 있음)
                if spec and spec.patterns:
                    # pattern 객체에 .regex가 있는지 확인 후 패턴 문자열 추출
                    spec_patterns_repr = [
                        p.regex.pattern if hasattr(p, 'regex') and p.regex else str(p)
                        for p in spec.patterns
                    ]
                    logger.debug(f"Successfully parsed {len(spec_patterns_repr)} patterns from {ignore_filename}: {spec_patterns_repr}")
                elif spec:
                    logger.debug(f"Parsed {ignore_filename}, but resulted in an empty PathSpec (maybe only comments?).")
                else: # spec 생성이 안된 경우 (이론상 발생 어려움)
                    logger.warning(f"pathspec.PathSpec.from_lines returned None or empty for {ignore_filename}, though lines were read.")

        except Exception as e:
            # WARNING: 파일 읽기 또는 파싱 중 오류 발생 시
            logger.warning(f"Could not read or parse {ignore_filename} at {ignore_path}: {e}", exc_info=True) # 에러 정보와 스택 트레이스 포함
            spec = None # 오류 발생 시 spec은 None 반환
    else:
        # DEBUG: Ignore 파일이 존재하지 않을 때 로깅
        logger.debug(f"Ignore file not found: {ignore_path}")

    return spec

# --- load_combined_ignore_spec 함수 ---
def load_combined_ignore_spec(root_dir: Path) -> pathspec.PathSpec:
    """
    .gitignore와 .pagrignore 파일을 로드하고 규칙을 결합하여 최종 PathSpec 객체를 반환합니다.
    .git 디렉토리는 항상 무시 목록에 포함됩니다.
    """
    logger.debug(f"Loading combined ignore specifications from root directory: {root_dir}")
    gitignore_spec = parse_ignore_file(root_dir, '.gitignore')
    pagrignore_spec = parse_ignore_file(root_dir, '.pagrignore')

    # 각 spec 객체에서 실제 패턴 문자열 리스트를 추출합니다.
    # PathSpec 객체가 None일 경우 빈 리스트를 사용합니다.
    gitignore_patterns_str = []
    if gitignore_spec and gitignore_spec.patterns:
        # .pattern 속성이 있는 경우만 사용 (GitWildMatchPattern 등)
        gitignore_patterns_str = [p.pattern for p in gitignore_spec.patterns if hasattr(p, 'pattern')]
        logger.debug(f"Extracted {len(gitignore_patterns_str)} patterns from gitignore_spec: {gitignore_patterns_str}")
    else:
        logger.debug("No patterns extracted from gitignore_spec (or spec was None/empty).")

    pagrignore_patterns_str = []
    if pagrignore_spec and pagrignore_spec.patterns:
        pagrignore_patterns_str = [p.pattern for p in pagrignore_spec.patterns if hasattr(p, 'pattern')]
        logger.debug(f"Extracted {len(pagrignore_patterns_str)} patterns from pagrignore_spec: {pagrignore_patterns_str}")
    else:
        logger.debug("No patterns extracted from pagrignore_spec (or spec was None/empty).")

    # 결합할 모든 패턴 문자열 리스트 생성 (.git/ 포함)
    # .git/는 디렉토리 매칭을 위해 끝에 슬래시 포함
    all_pattern_strings = ['.git/']
    all_pattern_strings.extend(gitignore_patterns_str)
    all_pattern_strings.extend(pagrignore_patterns_str)

    # 중복 제거 (선택적이지만 권장)
    unique_pattern_strings = sorted(list(set(all_pattern_strings)))
    if len(unique_pattern_strings) != len(all_pattern_strings):
        logger.debug(f"Removed {len(all_pattern_strings) - len(unique_pattern_strings)} duplicate patterns.")

    logger.debug(f"Total unique pattern strings being combined ({len(unique_pattern_strings)}): {unique_pattern_strings}")

    # 결합된 문자열 리스트로부터 최종 PathSpec 객체 생성
    # 여기서 unique_pattern_strings가 비어있으면 PathSpec([]) 와 같이 빈 Spec 객체가 생성됩니다.
    combined_spec = pathspec.PathSpec.from_lines('gitwildmatch', unique_pattern_strings)

    # 최종 결합된 Spec 객체 내부의 패턴 확인 (정규식 패턴으로 보일 수 있음)
    if combined_spec.patterns:
        final_patterns_repr = [
            p.regex.pattern if hasattr(p, 'regex') and p.regex else str(p)
            for p in combined_spec.patterns
        ]
        logger.debug(f"Final combined_spec object created with {len(final_patterns_repr)} patterns (regex form may appear): {final_patterns_repr}")
    else:
        logger.debug("Final combined_spec object created, but it contains no patterns.")
        # 이 경우는 보통 .git/ 만 포함될 때 발생

    # 추가 검사: ignore 파일이 있었는데 최종 패턴이 .git/ 뿐인지 확인
    # (주석이나 빈 라인만 있는 ignore 파일의 경우)
    if len(final_patterns_repr) <= 1 and (gitignore_spec or pagrignore_spec):
         logger.debug("Ignore files were found/parsed but the final combined spec only contains the default '.git/' rule (or is empty). Check ignore file contents (e.g., only comments?).")

    return combined_spec


# --- generate_tree 함수 ---
def generate_tree(root_dir: Path, combined_ignore_spec: pathspec.PathSpec) -> str:
    """
    주어진 디렉토리의 트리 구조 문자열을 생성합니다.
    결합된 ignore 규칙(.gitignore + .pagrignore + .git)을 제외합니다.
    """
    tree_lines = [f"{root_dir.name}/"] # 루트 디렉토리 이름으로 시작
    logger.debug(f"Generating directory tree for {root_dir}...")

    # 재귀 함수 정의
    def _build_tree_recursive(current_dir: Path, prefix: str):
        logger.debug(f"Building tree for directory: {current_dir} with prefix: '{prefix}'")
        try:
            # 현재 디렉토리의 항목들을 리스트로 가져와 정렬 (디렉토리 우선, 이름순)
            items = sorted(list(current_dir.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
            logger.debug(f"Found {len(items)} items in {current_dir}")
        except Exception as e:
            # 디렉토리 접근 오류 처리
            error_msg = f"[Error accessing directory: {e}]"
            tree_lines.append(f"{prefix}└── {error_msg}")
            logger.error(f"Error accessing directory {current_dir}: {e}", exc_info=False) # 스택 트레이스 제외 가능
            return

        # 무시 규칙에 해당하지 않는 항목만 필터링
        filtered_items = []
        for item in items:
            try:
                 # root_dir 기준으로 상대 경로 계산 (ignore 규칙과 비교하기 위함)
                 # is_relative_to 로 root_dir 벗어나는 경우 방지 (심볼릭 링크 등)
                 if item.is_relative_to(root_dir):
                     relative_path = item.relative_to(root_dir)
                     # pathspec은 POSIX 스타일 경로를 사용하므로 변환
                     relative_path_str = relative_path.as_posix()
                     # 디렉토리인 경우 매칭을 위해 끝에 '/' 추가 (gitignore 규칙과 동일하게)
                     if item.is_dir():
                         relative_path_str += '/'

                     # ignore 규칙과 매칭 확인
                     # combined_ignore_spec이 비어있을 수도 있으니 확인
                     should_ignore = combined_ignore_spec.match_file(relative_path_str) if combined_ignore_spec else False

                     # DEBUG: 각 경로와 무시 여부 로깅 (매우 상세할 수 있음)
                     logger.debug(f"Checking tree item: Path='{relative_path_str}', IsDir={item.is_dir()}, Ignored={should_ignore}")

                     if should_ignore:
                         logger.debug(f"Ignoring item based on rules: {relative_path_str}")
                         continue # 무시 대상이면 건너뛰기

                     # 무시되지 않으면 필터링된 리스트에 추가
                     filtered_items.append(item)
                 else:
                     # root_dir 외부에 있는 항목 경고 (예: 잘못된 심볼릭 링크)
                     logger.warning(f"Item {item} is not relative to root {root_dir}. Skipping in tree view.")

            except ValueError as ve:
                 # 상대 경로 계산 오류 (일반적으로 발생 안 함)
                 logger.warning(f"Could not determine relative path for {item} against {root_dir}: {ve}. Skipping.", exc_info=True)
            except Exception as e:
                 # 기타 예외 처리
                 logger.error(f"Error processing tree item {item}: {e}", exc_info=True)

        logger.debug(f"Filtered down to {len(filtered_items)} items in {current_dir} for tree display.")

        # 필터링된 항목들을 트리 형식으로 추가
        pointers = ["├── "] * (len(filtered_items) - 1) + ["└── "] # 마지막 항목은 다른 포인터 사용
        for pointer, item in zip(pointers, filtered_items):
            # 디렉토리면 이름 뒤에 '/' 추가
            display_name = f"{item.name}{'/' if item.is_dir() else ''}"
            tree_lines.append(f"{prefix}{pointer}{display_name}")
            # 현재 항목이 디렉토리면 재귀 호출
            if item.is_dir():
                # 다음 레벨의 prefix 결정 ('│ ' 또는 '  ')
                extension = "│   " if pointer == "├── " else "    "
                _build_tree_recursive(item, prefix + extension)

    # 최상위 디렉토리부터 재귀 함수 호출 시작
    _build_tree_recursive(root_dir, "")
    logger.debug("Finished generating tree structure.")
    return "\n".join(tree_lines) # 최종 트리 문자열 반환


# --- scan_and_filter_files 함수 ---
def scan_and_filter_files(root_dir: Path, combined_ignore_spec: pathspec.PathSpec) -> List[Path]:
    """
    root_dir 아래의 모든 파일을 재귀적으로 찾고, combined_ignore_spec 규칙에 따라 필터링합니다.
    결과로 root_dir 기준 상대 경로(Path 객체) 리스트를 반환합니다.
    """
    included_files: Set[Path] = set() # 중복 방지 및 빠른 조회를 위해 set 사용
    logger.debug(f"Scanning and filtering files within {root_dir}...")

    # rglob('*')을 사용하여 모든 파일과 디렉토리를 재귀적으로 탐색
    # 성능을 위해 Path.walk() 를 고려할 수도 있으나 rglob이 더 간결함
    for item in root_dir.rglob('*'):
        # 파일인 경우에만 처리
        if item.is_file():
            try:
                # root_dir 기준으로 상대 경로 계산 가능한지 확인
                if item.is_relative_to(root_dir):
                    relative_path = item.relative_to(root_dir)
                    # pathspec 비교를 위해 POSIX 경로 문자열 사용
                    relative_path_str = relative_path.as_posix()

                    # ignore 규칙과 매칭 확인
                    should_ignore = combined_ignore_spec.match_file(relative_path_str) if combined_ignore_spec else False

                    # DEBUG: 각 파일 경로와 무시 여부 로깅 (매우 상세할 수 있음)
                    logger.debug(f"Checking file: Path='{relative_path_str}', Ignored={should_ignore}")

                    if should_ignore:
                        logger.debug(f"Ignoring file based on rules: {relative_path_str}")
                        continue # 무시 대상 파일

                    # 무시되지 않으면 결과 set에 상대 경로(Path 객체) 추가
                    included_files.add(relative_path)
                    logger.debug(f"Including file: {relative_path_str}")
                else:
                     # root_dir 외부에 있는 파일 경고
                     logger.warning(f"Found file {item} which is not relative to root {root_dir}. Skipping.")

            except ValueError as ve:
                 # 상대 경로 계산 오류
                 logger.warning(f"Could not get relative path for file {item}: {ve}. Skipping.", exc_info=True)
            except Exception as e:
                 # 파일 처리 중 기타 예외
                 logger.error(f"Error processing file {item} during scan: {e}", exc_info=True)
        elif item.is_dir():
             # 디렉토리 자체는 포함 대상이 아니므로 무시
             # 단, 디렉토리에 대한 ignore 규칙은 위에서 파일/하위 디렉토리 처리 시 사용됨
             logger.debug(f"Skipping directory item during file scan: {item.relative_to(root_dir).as_posix()}/")
             pass


    logger.debug(f"Scan complete. Found {len(included_files)} files to be included after filtering.")
    # 최종 결과를 Path 객체 리스트로 변환하여 정렬 후 반환
    return sorted(list(included_files), key=lambda p: p.as_posix())


# --- aggregate_codes 함수 ---
def aggregate_codes(root_dir: Path, relative_paths: List[Path]) -> str:
    """
    주어진 상대 경로 파일들의 내용을 읽어 하나의 문자열로 합칩니다.
    각 파일 내용 앞에는 파일 경로 헤더를 추가하고, 마크다운 코드 블록으로 감쌉니다.
    """
    aggregated_content = [] # 각 파일의 포맷된 블록을 저장할 리스트
    # 파일 블록 사이의 구분자 정의
    separator = "\n\n" + "=" * 80 + "\n\n"
    logger.debug(f"Starting aggregation of {len(relative_paths)} files from root: {root_dir}")

    for relative_path in relative_paths:
        # 각 파일 블록의 헤더 생성 (POSIX 경로 사용)
        header = f"--- File: {relative_path.as_posix()} ---"
        # 파일의 전체 절대 경로 계산
        full_path = root_dir / relative_path
        formatted_block = "" # 현재 파일의 포맷된 블록 초기화
        logger.debug(f"Processing file for aggregation: {full_path}")

        try:
            # scan 이후 파일이 삭제되거나 타입이 변경되었을 수 있으므로 다시 확인
            if not full_path.is_file():
                 # 파일이 아니거나 사라진 경우 경고 로깅
                 logger.warning(f"Path {full_path} (relative: {relative_path.as_posix()}) was expected to be a file but is not (or disappeared). Skipping aggregation for this path.")
                 # 결과물에 에러 메시지 포함 (선택적)
                 error_message = f"[Warning: Expected file not found or is not a file at path: {full_path}]"
                 formatted_block = f"{header}\n\n{error_message}"
                 aggregated_content.append(formatted_block) # 에러 블록 추가
                 continue # 다음 파일로 이동

            # 파일 내용 읽기 (UTF-8 시도, 에러 시 대체 문자로)
            content = full_path.read_text(encoding='utf-8', errors='replace')
            logger.debug(f"Successfully read content from {full_path} ({len(content)} chars).")

            # 마크다운 코드 블록 언어 힌트 생성 (파일 확장자 기반)
            suffix = relative_path.suffix.lower() # 소문자 확장자 (.txt, .py 등)
            language_hint = suffix[1:] if suffix and suffix.startswith('.') else "" # 맨 앞 '.' 제거
            logger.debug(f"Using language hint '{language_hint}' for {relative_path.as_posix()}")

            # 마크다운 코드 블록 생성
            opening_fence = f"```{language_hint}"
            closing_fence = "```"
            # 헤더, 빈 줄, 코드 블록 시작, 내용, 코드 블록 끝 결합
            formatted_block = f"{header}\n\n{opening_fence}\n{content}\n{closing_fence}"

        except FileNotFoundError:
             # 이 경우는 위 is_file() 체크 후에도 발생 가능 (race condition)
             error_message = f"[Error: File disappeared unexpectedly: {full_path}]"
             formatted_block = f"{header}\n\n{error_message}"
             logger.error(f"File disappeared unexpectedly during aggregation: {full_path}", exc_info=False)
        except PermissionError:
            # 파일 읽기 권한 오류
            error_message = f"[Error: Permission denied reading file: {full_path}]"
            formatted_block = f"{header}\n\n{error_message}"
            logger.error(f"Permission denied reading file {full_path}", exc_info=False)
        except Exception as e:
            # 기타 파일 읽기 또는 처리 중 예외
            error_message = f"[Error reading or processing file: {e}]"
            formatted_block = f"{header}\n\n{error_message}"
            logger.error(f"Error reading or processing file {full_path}: {e}", exc_info=True) # 스택 트레이스 포함

        # 생성된 포맷 블록(성공 또는 에러 메시지)을 리스트에 추가
        aggregated_content.append(formatted_block)

    logger.debug(f"Finished processing all {len(relative_paths)} files for aggregation.")
    # 모든 파일의 포맷된 블록들을 최종 구분자로 합쳐서 하나의 문자열로 반환
    final_result = separator.join(aggregated_content)
    logger.debug(f"Total aggregated content length: {len(final_result)} characters.")
    return final_result