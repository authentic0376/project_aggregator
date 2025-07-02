# src/project_aggregator/logic.py
import pathspec
from pathlib import Path
from typing import Optional, List, Set
import logging

# 로거 인스턴스 가져오기 (logic 모듈용)
logger = logging.getLogger(__name__)


def load_combined_ignore_spec(root_dir: Path) -> pathspec.PathSpec:
    """
    .gitignore와 .pagrignore 파일을 로드하고 규칙을 순서대로 결합하여 최종 PathSpec 객체를 반환합니다.
    .pagrignore의 규칙이 .gitignore의 규칙을 덮어쓸 수 있습니다 (예: '!' 패턴).
    '.git/' 디렉토리는 항상 무시 목록에 기본으로 포함됩니다.
    """
    logger.debug(f"{root_dir}에서 통합 무시 규칙을 로드합니다.")
    all_patterns = ['.git/']  # .git 디렉토리는 항상 무시

    # .gitignore 파일 패턴 읽기
    gitignore_path = root_dir / '.gitignore'
    if gitignore_path.is_file():
        try:
            with gitignore_path.open('r', encoding='utf-8') as f:
                logger.debug(f"{gitignore_path}에서 패턴을 읽습니다.")
                gitignore_patterns = f.readlines()
                all_patterns.extend(gitignore_patterns)
        except Exception as e:
            logger.warning(f"'.gitignore' 파일을 읽는 중 오류 발생: {e}")

    # .pagrignore 파일 패턴 읽기
    pagrignore_path = root_dir / '.pagrignore'
    if pagrignore_path.is_file():
        try:
            with pagrignore_path.open('r', encoding='utf-8') as f:
                logger.debug(f"'.pagrignore'에서 패턴을 읽습니다.")
                pagrignore_patterns = f.readlines()
                all_patterns.extend(pagrignore_patterns)  # gitignore 규칙 다음에 추가하여 재정의 가능하게 함
        except Exception as e:
            logger.warning(f"'.pagrignore' 파일을 읽는 중 오류 발생: {e}")

    logger.debug(f"총 {len(all_patterns)}개의 패턴 라인(주석, 공백 포함)으로 PathSpec을 생성합니다.")

    # PathSpec.from_lines는 주석과 공백 라인을 알아서 처리합니다.
    combined_spec = pathspec.PathSpec.from_lines('gitwildmatch', all_patterns)

    if logger.isEnabledFor(logging.DEBUG):
        spec_patterns_repr = [
            p.pattern for p in combined_spec.patterns if hasattr(p, 'pattern')
        ]
        logger.debug(
            f"최종 결합된 PathSpec 객체가 {len(spec_patterns_repr)}개의 패턴으로 생성되었습니다: {spec_patterns_repr}")

    return combined_spec


def generate_tree(root_dir: Path, combined_ignore_spec: pathspec.PathSpec) -> str:
    """
    주어진 디렉토리의 트리 구조 문자열을 생성합니다.
    결합된 무시 규칙(.git 포함)을 적용하여 제외할 파일/디렉토리를 결정합니다.
    """
    tree_lines = [f"{root_dir.name}/"]
    logger.debug(f"{root_dir}의 디렉토리 트리를 생성합니다 (무시 규칙 적용됨).")

    def _build_tree_recursive(current_dir: Path, prefix: str):
        logger.debug(f"디렉토리 트리 빌드 중: {current_dir}, 접두사: '{prefix}'")
        try:
            # 항목들을 파일/디렉토리 순, 그 다음 이름순으로 정렬
            items = sorted(list(current_dir.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
            logger.debug(f"{current_dir}에서 {len(items)}개의 항목을 찾았습니다.")
        except Exception as e:
            error_msg = f"[디렉토리 접근 오류: {e}]"
            tree_lines.append(f"{prefix}└── {error_msg}")
            logger.error(f"디렉토리 {current_dir} 접근 중 오류 발생: {e}", exc_info=False)
            return

        filtered_items = []
        for item in items:
            try:
                if item.is_relative_to(root_dir):
                    relative_path = item.relative_to(root_dir)
                    # pathspec은 디렉토리를 나타낼 때 끝에 '/'가 있는 것을 선호합니다.
                    relative_path_str = relative_path.as_posix()
                    if item.is_dir():
                        relative_path_str += '/'

                    should_ignore = combined_ignore_spec.match_file(relative_path_str)
                    logger.debug(
                        f"트리 항목 확인: 경로='{relative_path_str}', 디렉토리?={item.is_dir()}, 무시?={should_ignore}")

                    if not should_ignore:
                        filtered_items.append(item)
                    else:
                        logger.debug(f"무시 규칙에 따라 트리에서 제외: {relative_path_str}")
                else:
                    logger.warning(f"항목 {item}이 루트 {root_dir}에 속하지 않아 트리에서 건너뜁니다.")
            except Exception as e:
                logger.error(f"트리 항목 {item} 처리 중 오류 발생: {e}", exc_info=True)

        logger.debug(f"{current_dir}의 {len(filtered_items)}개 항목이 트리 표시에 포함됩니다 (무시 규칙만 적용).")

        pointers = ["├── "] * (len(filtered_items) - 1) + ["└── "]
        for pointer, item in zip(pointers, filtered_items):
            display_name = f"{item.name}{'/' if item.is_dir() else ''}"
            tree_lines.append(f"{prefix}{pointer}{display_name}")
            if item.is_dir():
                extension = "│   " if pointer == "├── " else "    "
                _build_tree_recursive(item, prefix + extension)

    _build_tree_recursive(root_dir, "")
    logger.debug("디렉토리 트리 구조 생성 완료.")
    return "\n".join(tree_lines)


def scan_and_filter_files(
        root_dir: Path,
        combined_ignore_spec: pathspec.PathSpec,
        include_patterns: Optional[List[str]] = None
) -> List[Path]:
    """
    root_dir 아래의 모든 파일을 재귀적으로 찾고, 무시 규칙과 선택적인 포함 패턴에 따라 필터링합니다.
    결과로 root_dir 기준 상대 경로(Path 객체) 리스트를 반환합니다.
    """
    included_files: Set[Path] = set()
    logger.debug(f"{root_dir} 내에서 파일 스캔 및 필터링을 시작합니다...")
    if logger.isEnabledFor(logging.DEBUG):
        ignore_pats = [p.pattern for p in combined_ignore_spec.patterns if hasattr(p, 'pattern')]
        logger.debug(f"적용될 무시 패턴: {ignore_pats}")
    logger.debug(f"주어진 포함 패턴: {include_patterns}")

    # 포함 패턴이 있으면 PathSpec 객체 생성
    include_spec: Optional[pathspec.PathSpec] = None
    if include_patterns:
        try:
            valid_patterns = [p for p in include_patterns if p.strip()]
            if valid_patterns:
                include_spec = pathspec.PathSpec.from_lines('gitwildmatch', valid_patterns)
                logger.debug(f"포함 규칙 PathSpec 생성 완료: {valid_patterns}")
            else:
                logger.debug("포함 패턴이 주어졌지만 모두 비어있어 아무 파일도 포함되지 않습니다.")
                return []
        except Exception as e:
            logger.error(f"포함 패턴으로 PathSpec 객체 생성 실패 {include_patterns}: {e}", exc_info=True)
            return []

    for item in root_dir.rglob('*'):
        if item.is_file():
            try:
                if item.is_relative_to(root_dir):
                    relative_path = item.relative_to(root_dir)
                    relative_path_str = relative_path.as_posix()

                    # 1. 무시 규칙 확인
                    should_ignore = combined_ignore_spec.match_file(relative_path_str)
                    logger.debug(f"파일 확인: 경로='{relative_path_str}', 무시?={should_ignore}")

                    if should_ignore:
                        continue

                    # 2. 포함 패턴 확인 (패턴이 제공된 경우)
                    if include_spec:
                        should_include = include_spec.match_file(relative_path_str)
                        logger.debug(
                            f"포함 패턴과 비교: 경로='{relative_path_str}', 포함?={should_include}")
                        if not should_include:
                            continue  # 포함 패턴과 일치하지 않으면 건너뜀

                    # 모든 필터를 통과한 경우 파일 추가
                    included_files.add(relative_path)
                    logger.debug(f"파일 포함: {relative_path_str}")
                else:
                    logger.warning(f"루트 {root_dir}에 속하지 않는 파일 발견: {item}. 건너뜁니다.")
            except Exception as e:
                logger.error(f"파일 스캔 중 {item} 처리 오류: {e}", exc_info=True)

    if not included_files:
        logger.info("규칙 적용 후 취합할 파일이 없습니다.")
    else:
        logger.debug(f"스캔 완료. 필터링 후 {len(included_files)}개의 파일을 포함합니다.")

    return sorted(list(included_files), key=lambda p: p.as_posix())


def generate_inclusion_tree(
        root_dir: Path,
        included_files: List[Path],
        max_files_per_dir: int = 10,
) -> str:
    """
    포함될 파일 목록을 기반으로 트리 구조 문자열을 생성합니다.
    한 디렉토리에 파일이 너무 많으면 일부를 생략하고 '...'로 표시합니다.
    """
    if not included_files:
        return f"{root_dir.name}/\n└── (포함된 파일 없음)"

    all_paths = set(included_files)
    for p in included_files:
        all_paths.update(p.parents)
    if Path('.') in all_paths:
        all_paths.remove(Path('.'))

    dir_paths = {p for p in all_paths for child in all_paths if child.parent == p}
    tree_lines = [f"{root_dir.name}/"]

    def _build_tree_recursive(current_relative_dir: Path, prefix: str):
        children = sorted([p for p in all_paths if p.parent == current_relative_dir],
                          key=lambda p: (p in dir_paths, p.name))
        dirs = [p for p in children if p in dir_paths]
        files = [p for p in children if p not in dir_paths]

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

        if omitted_count > 0:
            connector = "└── "
            tree_lines.append(f"{prefix}{connector}... ({omitted_count}개 파일 생략)")

    _build_tree_recursive(Path('.'), "")
    return "\n".join(tree_lines)


def aggregate_codes(root_dir: Path, relative_paths: List[Path]) -> str:
    """
    주어진 상대 경로 파일들의 내용을 읽어 하나의 문자열로 합칩니다.
    각 파일 내용 앞에는 파일 경로 헤더를 추가하고, 마크다운 코드 블록으로 감쌉니다.
    """
    aggregated_content = []
    separator = "\n\n" + "=" * 80 + "\n\n"
    logger.debug(f"{root_dir}에서 {len(relative_paths)}개 파일의 취합을 시작합니다.")

    for relative_path in relative_paths:
        header = f"--- File: {relative_path.as_posix()} ---"
        full_path = root_dir / relative_path
        formatted_block = ""
        logger.debug(f"취합을 위해 {full_path} 파일을 처리합니다.")

        try:
            if not full_path.is_file():
                logger.warning(f"경로 {full_path}에 파일이 없습니다. 이 파일은 건너뜁니다.")
                error_message = f"[경고: 파일을 찾을 수 없거나 디렉토리입니다: {full_path}]"
                formatted_block = f"{header}\n\n{error_message}"
                aggregated_content.append(formatted_block)
                continue

            content = full_path.read_text(encoding='utf-8', errors='replace')
            logger.debug(f"{full_path}에서 {len(content)}자 길이의 내용을 읽었습니다.")

            suffix = relative_path.suffix.lower()
            language_hint = suffix[1:] if suffix and suffix.startswith('.') else ""
            logger.debug(f"{relative_path.as_posix()}에 대해 '{language_hint}' 언어 힌트를 사용합니다.")

            opening_fence = f"```{language_hint}"
            closing_fence = "```"
            formatted_block = f"{header}\n\n{opening_fence}\n{content}\n{closing_fence}"

        except Exception as e:
            error_message = f"[파일 처리 중 오류 발생: {e}]"
            formatted_block = f"{header}\n\n{error_message}"
            logger.error(f"{full_path} 파일 처리 중 오류 발생: {e}", exc_info=True)

        aggregated_content.append(formatted_block)

    logger.debug(f"총 {len(relative_paths)}개 파일의 취합 처리를 완료했습니다.")
    final_result = separator.join(aggregated_content)
    logger.debug(f"최종 취합된 내용의 총 길이는 {len(final_result)}자입니다.")
    return final_result