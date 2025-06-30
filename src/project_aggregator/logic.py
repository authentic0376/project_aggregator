# src/project_aggregator/logic.py
import pathspec
from pathlib import Path
from typing import Optional, List, Set, Tuple
import sys
import os
import logging  # 로깅 모듈 임포트

# 로거 인스턴스 가져오기 (logic 모듈용)
logger = logging.getLogger(__name__)


# --- parse_ignore_file 함수 ---
def parse_ignore_file(root_dir: Path, ignore_filename: str) -> Optional[pathspec.PathSpec]:
    """
    지정된 ignore 파일을 파싱하여 pathspec 객체를 반환합니다.
    없거나 읽을 수 없으면 None을 반환합니다.
    """
    ignore_path = root_dir / ignore_filename
    spec = None
    logger.debug(f"Attempting to parse ignore file: {ignore_path}")

    if ignore_path.is_file():
        logger.debug(f"Found ignore file: {ignore_path}")
        try:
            with open(ignore_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                read_lines = [line.strip() for line in lines if line.strip()]

                logger.debug(f"Stripped non-empty lines from {ignore_filename}: {read_lines}")

                if not read_lines:
                    logger.debug(
                        f"{ignore_filename} is empty or contains only whitespace after stripping. No patterns to parse.")
                    return None

                spec = pathspec.PathSpec.from_lines('gitwildmatch', read_lines)

                if spec and spec.patterns:
                    spec_patterns_repr = [
                        p.regex.pattern if hasattr(p, 'regex') and p.regex else str(p)
                        for p in spec.patterns
                    ]
                    logger.debug(
                        f"Successfully parsed {len(spec_patterns_repr)} patterns from {ignore_filename}: {spec_patterns_repr}")
                elif spec:
                    logger.debug(f"Parsed {ignore_filename}, but resulted in an empty PathSpec (maybe only comments?).")
                else:
                    logger.warning(
                        f"pathspec.PathSpec.from_lines returned None or empty for {ignore_filename}, though lines were read.")

        except Exception as e:
            logger.warning(f"Could not read or parse {ignore_filename} at {ignore_path}: {e}", exc_info=True)
            spec = None
    else:
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

    gitignore_patterns_str = []
    if gitignore_spec and gitignore_spec.patterns:
        gitignore_patterns_str = [p.pattern for p in gitignore_spec.patterns if hasattr(p, 'pattern')]
        logger.debug(f"Extracted {len(gitignore_patterns_str)} patterns from gitignore_spec: {gitignore_patterns_str}")
    else:
        logger.debug("No patterns extracted from gitignore_spec (or spec was None/empty).")

    pagrignore_patterns_str = []
    if pagrignore_spec and pagrignore_spec.patterns:
        pagrignore_patterns_str = [p.pattern for p in pagrignore_spec.patterns if hasattr(p, 'pattern')]
        logger.debug(
            f"Extracted {len(pagrignore_patterns_str)} patterns from pagrignore_spec: {pagrignore_patterns_str}")
    else:
        logger.debug("No patterns extracted from pagrignore_spec (or spec was None/empty).")

    all_pattern_strings = ['.git/']
    all_pattern_strings.extend(gitignore_patterns_str)
    all_pattern_strings.extend(pagrignore_patterns_str)

    unique_pattern_strings = sorted(list(set(all_pattern_strings)))
    if len(unique_pattern_strings) != len(all_pattern_strings):
        logger.debug(f"Removed {len(all_pattern_strings) - len(unique_pattern_strings)} duplicate patterns.")

    logger.debug(
        f"Total unique pattern strings being combined ({len(unique_pattern_strings)}): {unique_pattern_strings}")

    combined_spec = pathspec.PathSpec.from_lines('gitwildmatch', unique_pattern_strings)

    if combined_spec.patterns:
        final_patterns_repr = [
            p.regex.pattern if hasattr(p, 'regex') and p.regex else str(p)
            for p in combined_spec.patterns
        ]
        logger.debug(
            f"Final combined_spec object created with {len(final_patterns_repr)} patterns (regex form may appear): {final_patterns_repr}")
    else:
        logger.debug("Final combined_spec object created, but it contains no patterns.")

    if len(final_patterns_repr) <= 1 and (gitignore_spec or pagrignore_spec):
        logger.debug(
            "Ignore files were found/parsed but the final combined spec only contains the default '.git/' rule (or is empty). Check ignore file contents (e.g., only comments?).")

    return combined_spec


# --- generate_tree 함수 ---
# 참고: 현재 트리 생성은 include_patterns를 고려하지 않고, ignore 규칙만 적용합니다.
# 이는 사용자가 지정한 패턴에 포함되지 않는 디렉토리 구조도 볼 수 있게 하기 위함입니다.
def generate_tree(root_dir: Path, combined_ignore_spec: pathspec.PathSpec) -> str:
    """
    주어진 디렉토리의 트리 구조 문자열을 생성합니다.
    결합된 ignore 규칙(.gitignore + .pagrignore + .git)을 제외합니다.
    (참고: 현재 이 함수는 명시적 '포함' 규칙은 적용하지 않습니다.)
    """
    tree_lines = [f"{root_dir.name}/"]
    logger.debug(
        f"Generating directory tree for {root_dir} (ignores applied, includes not applied to tree structure itself)...")

    def _build_tree_recursive(current_dir: Path, prefix: str):
        logger.debug(f"Building tree for directory: {current_dir} with prefix: '{prefix}'")
        try:
            items = sorted(list(current_dir.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
            logger.debug(f"Found {len(items)} items in {current_dir}")
        except Exception as e:
            error_msg = f"[Error accessing directory: {e}]"
            tree_lines.append(f"{prefix}└── {error_msg}")
            logger.error(f"Error accessing directory {current_dir}: {e}", exc_info=False)
            return

        filtered_items = []
        for item in items:
            try:
                if item.is_relative_to(root_dir):
                    relative_path = item.relative_to(root_dir)
                    relative_path_str = relative_path.as_posix()
                    if item.is_dir():
                        relative_path_str += '/'

                    should_ignore = combined_ignore_spec.match_file(
                        relative_path_str) if combined_ignore_spec else False

                    logger.debug(
                        f"Checking tree item: Path='{relative_path_str}', IsDir={item.is_dir()}, Ignored={should_ignore}")

                    if should_ignore:
                        logger.debug(f"Ignoring tree item based on rules: {relative_path_str}")
                        continue

                    # TODO: 여기서 include_patterns 기반 필터링을 추가할 수 있으나,
                    # 현재 요구사항은 파일 내용 집계에만 적용하는 것이므로 트리에는 적용 안 함.
                    filtered_items.append(item)
                else:
                    logger.warning(f"Item {item} is not relative to root {root_dir}. Skipping in tree view.")

            except ValueError as ve:
                logger.warning(f"Could not determine relative path for {item} against {root_dir}: {ve}. Skipping.",
                               exc_info=True)
            except Exception as e:
                logger.error(f"Error processing tree item {item}: {e}", exc_info=True)

        logger.debug(
            f"Filtered down to {len(filtered_items)} items in {current_dir} for tree display (based on ignores only).")

        pointers = ["├── "] * (len(filtered_items) - 1) + ["└── "]
        for pointer, item in zip(pointers, filtered_items):
            display_name = f"{item.name}{'/' if item.is_dir() else ''}"
            tree_lines.append(f"{prefix}{pointer}{display_name}")
            if item.is_dir():
                extension = "│   " if pointer == "├── " else "   "
                _build_tree_recursive(item, prefix + extension)

    _build_tree_recursive(root_dir, "")
    logger.debug("Finished generating tree structure.")
    return "\n".join(tree_lines)


# --- scan_and_filter_files 함수 ---
def scan_and_filter_files(
        root_dir: Path,
        combined_ignore_spec: pathspec.PathSpec,
        include_patterns: Optional[List[str]] = None
) -> List[Path]:
    """
    root_dir 아래의 모든 파일을 재귀적으로 찾고, ignore 규칙과 선택적인 include 패턴에 따라 필터링합니다.
    결과로 root_dir 기준 상대 경로(Path 객체) 리스트를 반환합니다.
    """
    included_files: Set[Path] = set()
    logger.debug(f"Scanning and filtering files within {root_dir}...")
    logger.debug(
        f"Ignore spec patterns being used: {[p.pattern for p in combined_ignore_spec.patterns if hasattr(p, 'pattern')] if combined_ignore_spec else 'None'}")
    logger.debug(f"Include patterns provided: {include_patterns}")

    # 포함 패턴이 있으면 PathSpec 객체 생성
    include_spec: Optional[pathspec.PathSpec] = None
    if include_patterns:
        try:
            # 비어있지 않은 패턴만 사용
            valid_patterns = [p for p in include_patterns if p.strip()]
            if valid_patterns:
                include_spec = pathspec.PathSpec.from_lines('gitwildmatch', valid_patterns)
                logger.debug(f"Created include spec with patterns: {valid_patterns}")
            else:
                logger.debug("Include patterns were provided but all were empty or whitespace.")
                # 유효한 패턴이 없으면 아무것도 포함하지 않음 -> 빈 리스트 반환
                return []
        except Exception as e:
            logger.error(f"Failed to create PathSpec from include patterns {include_patterns}: {e}", exc_info=True)
            # 패턴 파싱 실패 시 오류를 발생시키거나 빈 리스트 반환 결정 필요
            # 여기서는 빈 리스트 반환
            return []

    for item in root_dir.rglob('*'):
        if item.is_file():
            try:
                if item.is_relative_to(root_dir):
                    relative_path = item.relative_to(root_dir)
                    relative_path_str = relative_path.as_posix()

                    # 1. Ignore 규칙 확인
                    should_ignore = combined_ignore_spec.match_file(
                        relative_path_str) if combined_ignore_spec else False
                    logger.debug(f"Checking file: Path='{relative_path_str}', Ignored={should_ignore}")

                    if should_ignore:
                        logger.debug(f"Ignoring file based on ignore rules: {relative_path_str}")
                        continue

                    # 2. Include 패턴 확인 (패턴이 제공된 경우)
                    if include_spec:
                        should_include = include_spec.match_file(relative_path_str)
                        logger.debug(
                            f"Checking file against include patterns: Path='{relative_path_str}', Included={should_include}")
                        if not should_include:
                            logger.debug(f"Skipping file not matching include patterns: {relative_path_str}")
                            continue
                    # else: include_spec이 없으면(패턴 미제공) 이 검사는 통과

                    # 모든 필터 통과 시 파일 추가
                    included_files.add(relative_path)
                    logger.debug(f"Including file: {relative_path_str}")
                else:
                    logger.warning(f"Found file {item} which is not relative to root {root_dir}. Skipping.")

            except ValueError as ve:
                logger.warning(f"Could not get relative path for file {item}: {ve}. Skipping.", exc_info=True)
            except Exception as e:
                logger.error(f"Error processing file {item} during scan: {e}", exc_info=True)
        elif item.is_dir():
            # 디렉토리 처리 로직은 현재 파일 스캔에선 불필요
            pass

    # 포함 패턴이 있었지만 결과가 비어있는 경우 추가 로깅
    if include_spec and not included_files:
        logger.info(
            "Include patterns were specified, but no files matched after applying both include and ignore rules.")
    elif not included_files:
        logger.info(
            "No files found to include after applying ignore rules (no include patterns were specified or matched).")
    else:
        logger.debug(f"Scan complete. Found {len(included_files)} files to be included after filtering.")

    return sorted(list(included_files), key=lambda p: p.as_posix())


def generate_inclusion_tree(
        root_dir: Path,
        included_files: List[Path],
        max_files_per_dir: int = 10,
) -> str:
    """
    포함될 파일 목록을 기반으로 트리 구조 문자열을 생성합니다.
    한 디렉토리에 파일이 너무 많으면 일부를 생략하고 '...'로 표시합니다.

    Args:
        root_dir: 프로젝트 루트 디렉토리.
        included_files: 포함될 파일들의 상대 경로 리스트.
        max_files_per_dir: 디렉토리당 표시할 최대 파일 수.

    Returns:
        파일 목록을 나타내는 트리 구조의 문자열.
    """
    if not included_files:
        return f"{root_dir.name}/\n└── (포함할 파일 없음)"

    # 모든 파일 경로와 그 부모 디렉토리 경로들을 집합에 추가
    all_paths = set(included_files)
    for p in included_files:
        all_paths.update(p.parents)
    # '.'는 현재 디렉토리를 의미하므로, 트리 구조에서는 제외
    if Path('.') in all_paths:
        all_paths.remove(Path('.'))

    # is_dir()은 파일 시스템을 조회하므로, 경로 정보만으로 디렉토리 여부 판단
    dir_paths = {p for p in all_paths for child in all_paths if child.parent == p}
    tree_lines = [f"{root_dir.name}/"]

    def _build_tree_recursive(current_relative_dir: Path, prefix: str):
        # 현재 디렉토리의 직계 자식들을 찾음
        children = [p for p in all_paths if p.parent == current_relative_dir]

        # 자식들을 디렉토리와 파일로 분리하고 이름순으로 정렬
        dirs = sorted([p for p in children if p in dir_paths], key=lambda p: p.name)
        files = sorted([p for p in children if p not in dir_paths], key=lambda p: p.name)

        # 파일 개수 제한 적용
        omitted_count = 0
        if max_files_per_dir >= 0 and len(files) > max_files_per_dir:
            omitted_count = len(files) - max_files_per_dir
            files = files[:max_files_per_dir]

        items_to_render = dirs + files

        for i, item in enumerate(items_to_render):
            is_last = (i == len(items_to_render) - 1) and (omitted_count == 0)
            connector = "└── " if is_last else "├── "

            if item in dir_paths:
                tree_lines.append(f"{prefix}{connector}{item.name}/")
                extension = "    " if is_last else "│   "
                _build_tree_recursive(item, prefix + extension)
            else:  # 파일
                tree_lines.append(f"{prefix}{connector}{item.name}")

        # 생략된 파일 정보 추가
        if omitted_count > 0:
            connector = "└── "
            tree_lines.append(f"{prefix}{connector}... ({omitted_count}개 파일 생략)")

    # 루트부터 재귀적으로 트리 빌드 시작. 상대경로의 시작점은 '.'
    _build_tree_recursive(Path('.'), "")

    return "\n".join(tree_lines)


# --- aggregate_codes 함수 ---
def aggregate_codes(root_dir: Path, relative_paths: List[Path]) -> str:
    """
    주어진 상대 경로 파일들의 내용을 읽어 하나의 문자열로 합칩니다.
    각 파일 내용 앞에는 파일 경로 헤더를 추가하고, 마크다운 코드 블록으로 감쌉니다.
    """
    aggregated_content = []
    separator = "\n\n" + "=" * 80 + "\n\n"
    logger.debug(f"Starting aggregation of {len(relative_paths)} files from root: {root_dir}")

    for relative_path in relative_paths:
        header = f"--- File: {relative_path.as_posix()} ---"
        full_path = root_dir / relative_path
        formatted_block = ""
        logger.debug(f"Processing file for aggregation: {full_path}")

        try:
            if not full_path.is_file():
                logger.warning(
                    f"Path {full_path} (relative: {relative_path.as_posix()}) was expected to be a file but is not (or disappeared). Skipping aggregation for this path.")
                error_message = f"[Warning: Expected file not found or is not a file at path: {full_path}]"
                formatted_block = f"{header}\n\n{error_message}"
                aggregated_content.append(formatted_block)
                continue

            content = full_path.read_text(encoding='utf-8', errors='replace')
            logger.debug(f"Successfully read content from {full_path} ({len(content)} chars).")

            suffix = relative_path.suffix.lower()
            language_hint = suffix[1:] if suffix and suffix.startswith('.') else ""
            logger.debug(f"Using language hint '{language_hint}' for {relative_path.as_posix()}")

            opening_fence = f"```{language_hint}"
            closing_fence = "```"
            formatted_block = f"{header}\n\n{opening_fence}\n{content}\n{closing_fence}"

        except FileNotFoundError:
            error_message = f"[Error: File disappeared unexpectedly: {full_path}]"
            formatted_block = f"{header}\n\n{error_message}"
            logger.error(f"File disappeared unexpectedly during aggregation: {full_path}", exc_info=False)
        except PermissionError:
            error_message = f"[Error: Permission denied reading file: {full_path}]"
            formatted_block = f"{header}\n\n{error_message}"
            logger.error(f"Permission denied reading file {full_path}", exc_info=False)
        except Exception as e:
            error_message = f"[Error reading or processing file: {e}]"
            formatted_block = f"{header}\n\n{error_message}"
            logger.error(f"Error reading or processing file {full_path}: {e}", exc_info=True)

        aggregated_content.append(formatted_block)

    logger.debug(f"Finished processing all {len(relative_paths)} files for aggregation.")
    final_result = separator.join(aggregated_content)
    logger.debug(f"Total aggregated content length: {len(final_result)} characters.")
    return final_result