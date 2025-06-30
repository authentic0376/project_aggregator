# src/project_aggregator/main.py
import typer
from pathlib import Path
from typing_extensions import Annotated
import sys
import os
from platformdirs import user_downloads_dir  # 다운로드 폴더 경로용
import subprocess  # 편집기 실행 대안 (typer.launch가 안될 경우)
from typing import Optional, List  # List 추가
import logging  # 로깅 모듈 임포트

# 로깅 설정 로더 임포트 및 설정 적용
from .logging_config import setup_logging

setup_logging()

# 로거 인스턴스 가져오기 (main 모듈용)
logger = logging.getLogger(__name__)

# logic 모듈의 함수들을 가져옵니다.
from .logic import (
    load_combined_ignore_spec,
    load_patterns_from_file,
    scan_and_filter_files,
    generate_tree,
    generate_inclusion_tree,
    aggregate_codes,
)

# 버전 정보 가져오기
try:
    from importlib.metadata import version

    __version__ = version("project_aggregator")
except ImportError:
    __version__ = "0.2.0"  # fallback (pyproject.toml 버전과 일치)

# --- Typer 앱 생성 및 기본 설정 ---
app = typer.Typer(
    name="pagr",  # 명령어 이름 설정
    help="프로젝트 파일을 집계합니다. 'run'은 무시 기반, 'run-only'는 포함 기반으로 동작합니다.",
    add_completion=False,
    no_args_is_help=True,  # 인자 없이 실행 시 도움말 표시
)

# --- 공통 옵션 ---
# 여러 명령어에서 중복되는 옵션들을 변수로 정의
RootPathOption = Annotated[Optional[Path], typer.Option(
    "--root", "-r",
    help="탐색을 시작할 루트 디렉토리. (기본값: 현재 디렉토리)",
    exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True,
    show_default=False,
)]

OutputPathOption = Annotated[Optional[Path], typer.Option(
    "--output", "-o",
    help="결과를 저장할 텍스트 파일 경로. (기본값: 다운로드 폴더의 pagr_output.txt)",
    resolve_path=True, dir_okay=False, file_okay=True,
)]

IncludePatternsArgument = Annotated[Optional[List[str]], typer.Argument(
    help="루트 디렉토리 내에서 포함할 파일/폴더의 상대 경로 또는 Glob 패턴. 생략 시 무시된 파일을 제외한 모든 파일이 대상이 됩니다.",
    show_default=False,
)]


# --- 버전 콜백 함수 ---
def version_callback(value: bool):
    if value:
        typer.echo(f"pagr version: {__version__}")
        raise typer.Exit()


@app.callback()
def main_options(
        version: Annotated[Optional[bool], typer.Option(
            "--version", "-v", help="버전 정보를 표시하고 종료합니다.",
            callback=version_callback, is_eager=True
        )] = None,
):
    """
    pagr: 프로젝트 파일 구조와 코드를 하나의 텍스트 파일로 합쳐주는 도구
    """
    pass


# --- 'run-only' 하위 명령어 ---
@app.command(name="run-only")
def run_only(
        root_path: RootPathOption = None,
        output_path: OutputPathOption = None,
):
    """
    (.pagronly 기반) 지정된 패턴의 파일만 취합하여 저장합니다.
    """
    logger.info("Starting 'run-only' command.")

    try:
        effective_root_dir = root_path if root_path else Path.cwd()
        logger.debug(f"Effective root directory set to: {effective_root_dir}")
        typer.echo(f"루트 디렉토리: {effective_root_dir}")

        # .pagronly 파일에서 포함할 패턴 로드
        only_patterns = load_patterns_from_file(effective_root_dir, ".pagronly")
        if not only_patterns:
            typer.secho("오류: '.pagronly' 파일을 찾을 수 없거나, 파일 내에 유효한 포함 패턴이 없습니다.", fg=typer.colors.RED, err=True)
            typer.secho("도움말: 'pagr only' 명령어를 사용하여 포함할 파일 패턴을 먼저 정의해주세요.", fg=typer.colors.YELLOW, err=True)
            raise typer.Exit(code=1)

        typer.echo(f"포함 규칙 파일: .pagronly")

        # 무시 규칙 로드 및 파일 스캔
        combined_ignore_spec = load_combined_ignore_spec(effective_root_dir)
        logger.info("Scanning project files based on .pagronly patterns...")
        relative_code_paths = scan_and_filter_files(
            effective_root_dir,
            combined_ignore_spec,
            only_patterns
        )
        logger.info(f"Scan complete. Found {len(relative_code_paths)} files to include.")

        # 출력 경로 설정
        if output_path is None:
            try:
                downloads_dir = Path(user_downloads_dir())
                downloads_dir.mkdir(parents=True, exist_ok=True)
                output_path = downloads_dir / "pagr_output.txt"
            except Exception as e:
                logger.warning(f"다운로드 폴더를 찾거나 생성할 수 없어({e}), 현재 폴더에 출력합니다.", exc_info=False)
                output_path = Path.cwd() / "pagr_output.txt"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        typer.echo(f"출력 파일: {output_path}")

        if not relative_code_paths:
            typer.secho("경고: 취합할 파일이 없습니다. (.pagronly 패턴과 일치하고 무시 규칙에 해당하지 않는 파일이 없습니다.)", fg=typer.colors.YELLOW,
                        err=True)

        # 결과물 생성 및 저장
        logger.info("Generating directory tree...")
        tree_output = generate_tree(effective_root_dir, combined_ignore_spec)

        logger.info(f"Aggregating content of {len(relative_code_paths)} file(s)...")
        code_output = aggregate_codes(effective_root_dir,
                                      relative_code_paths) if relative_code_paths else "[취합 대상으로 선택된 파일이 없습니다]"

        final_output = (
            f"========================================\n"
            f" Project Root: {effective_root_dir}\n"
            f"========================================\n\n"
            f"========================================\n"
            f"        Project Directory Tree\n"
            f"   (Ignoring .git, .gitignore, .pagrignore)\n"
            f"========================================\n\n"
            f"{tree_output}\n\n\n"
            f"========================================\n"
            f"           Aggregated Code Files\n"
            f"   (Included: patterns from .pagronly)\n"
            f"========================================\n\n"
            f"{code_output}\n"
        )

        logger.info(f"Writing output to: {output_path} ...")
        output_path.write_text(final_output, encoding='utf-8')
        typer.secho(f"성공적으로 파일을 생성했습니다: {output_path}", fg=typer.colors.GREEN)

    except typer.Exit:
        raise
    except Exception as e:
        logger.critical(f"'run-only' 명령어 실행 중 예상치 못한 오류 발생: {e}", exc_info=True)
        typer.secho(f"예상치 못한 오류가 발생했습니다: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- 'run' 하위 명령어 ---
@app.command()
def run(
        include_patterns: IncludePatternsArgument = None,
        root_path: RootPathOption = None,
        output_path: OutputPathOption = None,
):
    """
    (기본 모드) 무시 규칙을 제외한 모든 파일을 취합하여 저장합니다.
    """
    logger.info("Starting 'run' command.")

    try:
        effective_root_dir = root_path if root_path else Path.cwd()
        logger.debug(f"Effective root directory set to: {effective_root_dir}")

        typer.echo(f"루트 디렉토리: {effective_root_dir}")
        if include_patterns:
            typer.echo(f"포함할 파일 패턴 (인자): {', '.join(include_patterns)}")

        combined_ignore_spec = load_combined_ignore_spec(effective_root_dir)

        logger.info("Scanning project files...")
        relative_code_paths = scan_and_filter_files(
            effective_root_dir,
            combined_ignore_spec,
            include_patterns
        )
        logger.info(f"Scan complete. Found {len(relative_code_paths)} files to include.")

        if output_path is None:
            try:
                downloads_dir = Path(user_downloads_dir())
                downloads_dir.mkdir(parents=True, exist_ok=True)
                output_path = downloads_dir / "pagr_output.txt"
            except Exception as e:
                logger.warning(f"다운로드 폴더를 찾거나 생성할 수 없어({e}), 현재 폴더에 출력합니다.", exc_info=False)
                output_path = Path.cwd() / "pagr_output.txt"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        typer.echo(f"출력 파일: {output_path}")

        if not relative_code_paths:
            typer.secho("경고: 취합할 파일이 없습니다.", fg=typer.colors.YELLOW, err=True)

        logger.info("Generating directory tree...")
        tree_output = generate_tree(effective_root_dir, combined_ignore_spec)

        logger.info(f"Aggregating content of {len(relative_code_paths)} file(s)...")
        code_output = aggregate_codes(effective_root_dir,
                                      relative_code_paths) if relative_code_paths else "[취합 대상으로 선택된 파일이 없습니다]"

        included_display = 'patterns from arguments' if include_patterns else 'All non-ignored files'

        final_output = (
            f"========================================\n"
            f" Project Root: {effective_root_dir}\n"
            f"========================================\n\n"
            f"========================================\n"
            f"        Project Directory Tree\n"
            f"   (Ignoring .git, .gitignore, .pagrignore)\n"
            f"========================================\n\n"
            f"{tree_output}\n\n\n"
            f"========================================\n"
            f"           Aggregated Code Files\n"
            f"   (Included: {included_display})\n"
            f"========================================\n\n"
            f"{code_output}\n"
        )

        logger.info(f"Writing output to: {output_path} ...")
        output_path.write_text(final_output, encoding='utf-8')
        typer.secho(f"성공적으로 파일을 생성했습니다: {output_path}", fg=typer.colors.GREEN)

    except typer.Exit:
        raise
    except Exception as e:
        logger.critical(f"'run' 명령어 실행 중 예상치 못한 오류 발생: {e}", exc_info=True)
        typer.secho(f"예상치 못한 오류가 발생했습니다: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- 'preview-only' 하위 명령어 ---
@app.command(name="preview-only")
def preview_only(
        root_path: RootPathOption = None,
        max_files: Annotated[int, typer.Option(
            "--max-files", help="각 디렉토리마다 표시할 최대 파일 수."
        )] = 10,
):
    """
    'run-only' 실행 시 어떤 파일들이 취합될지 미리 봅니다.
    """
    logger.info("Starting 'preview-only' command.")
    try:
        effective_root_dir = root_path if root_path else Path.cwd()
        logger.debug(f"Effective root directory set to: {effective_root_dir}")

        only_patterns = load_patterns_from_file(effective_root_dir, ".pagronly")
        if not only_patterns:
            typer.secho("오류: '.pagronly' 파일을 찾을 수 없거나, 파일 내에 유효한 포함 패턴이 없습니다.", fg=typer.colors.RED, err=True)
            typer.secho("도움말: 'pagr only' 명령어를 사용하여 포함할 파일 패턴을 먼저 정의해주세요.", fg=typer.colors.YELLOW, err=True)
            raise typer.Exit(code=1)

        combined_ignore_spec = load_combined_ignore_spec(effective_root_dir)
        relative_code_paths = scan_and_filter_files(effective_root_dir, combined_ignore_spec, only_patterns)

        typer.secho(f"\n[Preview for run-only] 총 {len(relative_code_paths)}개의 파일이 취합 대상입니다. (.pagronly 기준)",
                    fg=typer.colors.CYAN, bold=True)
        inclusion_tree = generate_inclusion_tree(effective_root_dir, relative_code_paths, max_files_per_dir=max_files)
        typer.echo(inclusion_tree)

    except Exception as e:
        logger.error(f"An unexpected error occurred during 'preview-only': {e}", exc_info=True)
        typer.secho(f"미리보기 중 오류가 발생했습니다: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- 'preview' 하위 명령어 ---
@app.command()
def preview(
        include_patterns: IncludePatternsArgument = None,
        root_path: RootPathOption = None,
        max_files: Annotated[int, typer.Option(
            "--max-files", help="각 디렉토리마다 표시할 최대 파일 수."
        )] = 10,
):
    """
    (기본 모드) 'run' 실행 시 어떤 파일들이 취합될지 미리 봅니다.
    """
    logger.info("Starting 'preview' command.")

    try:
        effective_root_dir = root_path if root_path else Path.cwd()
        logger.debug(f"Effective root directory set to: {effective_root_dir}")

        combined_ignore_spec = load_combined_ignore_spec(effective_root_dir)

        logger.info("Scanning project files for preview...")
        relative_code_paths = scan_and_filter_files(
            effective_root_dir,
            combined_ignore_spec,
            include_patterns
        )

        typer.secho(f"\n[Preview for run] 총 {len(relative_code_paths)}개의 파일이 취합 대상입니다.", fg=typer.colors.CYAN,
                    bold=True)

        inclusion_tree = generate_inclusion_tree(
            effective_root_dir,
            relative_code_paths,
            max_files_per_dir=max_files
        )
        typer.echo(inclusion_tree)

    except Exception as e:
        logger.error(f"An unexpected error occurred during 'preview': {e}", exc_info=True)
        typer.secho(f"미리보기 중 오류가 발생했습니다: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


DEFAULT_PAGRONLY_CONTENT = """\
# 포함할 파일이나 디렉토리의 패턴을 한 줄에 하나씩 입력하세요.
# Glob 패턴(e.g., src/**/*.py, *.md)을 사용할 수 있습니다.
# 이 파일은 'pagr run-only' 명령어 실행 시 사용됩니다.
# '#'으로 시작하는 줄은 주석 처리됩니다.

# --- 예시 ---
# src/
# tests/
# README.md
# pyproject.toml
"""


@app.command()
def only():
    """
    (run-only용) 포함 규칙 파일(.pagronly)을 열거나 생성합니다.
    """
    only_file_path = Path.cwd() / ".pagronly"
    logger.info(f"Executing 'only' command for path: {only_file_path}")

    try:
        if not only_file_path.exists():
            only_file_path.write_text(DEFAULT_PAGRONLY_CONTENT, encoding='utf-8')
            typer.secho(f"'{only_file_path.name}' 파일을 기본 내용으로 생성했습니다.", fg=typer.colors.GREEN)

        typer.echo(f"기본 편집기에서 '{only_file_path.name}' 파일을 엽니다...")

        try:
            typer.launch(str(only_file_path), locate=False)
        except Exception:
            try:
                if sys.platform == "win32":
                    os.startfile(str(only_file_path))
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(only_file_path)], check=True)
                else:
                    subprocess.run(["xdg-open", str(only_file_path)], check=True)
            except Exception as e_os:
                logger.error(f"모든 자동 열기 시도 실패: {e_os}", exc_info=True)
                typer.secho("편집기를 자동으로 열 수 없습니다.", fg=typer.colors.YELLOW)
                typer.echo(f"아래 경로의 파일을 직접 열어주세요:\n{only_file_path}")

    except Exception as e:
        logger.error(f".pagronly 명령어 처리 중 오류 발생: {e}", exc_info=True)
        typer.secho(f".pagronly 처리 중 오류 발생: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# 'ignore' 명령어에 대한 기본 내용
DEFAULT_PAGRIGNORE_CONTENT = """\
# pagr이 항상 무시할 패턴을 추가합니다. .gitignore와 유사하게 동작합니다.
# 이 파일은 Git으로 관리할 필요가 없는, pagr 도구만을 위한 무시 규칙을 정의하기 좋습니다.
poetry.lock
tests/
.venv/
.idea/
*.pyc
"""


@app.command()
def ignore():
    """
    (전체 적용) 무시 규칙 파일(.pagrignore)을 열거나 생성합니다.
    """
    ignore_file_path = Path.cwd() / ".pagrignore"
    logger.info(f"Executing 'ignore' command for path: {ignore_file_path}")

    try:
        if not ignore_file_path.exists():
            ignore_file_path.write_text(DEFAULT_PAGRIGNORE_CONTENT, encoding='utf-8')
            typer.secho(f"'{ignore_file_path.name}' 파일을 기본 내용으로 생성했습니다.", fg=typer.colors.GREEN)

        typer.echo(f"기본 편집기에서 '{ignore_file_path.name}' 파일을 엽니다...")

        try:
            typer.launch(str(ignore_file_path), locate=False)
        except Exception:
            try:
                if sys.platform == "win32":
                    os.startfile(str(ignore_file_path))
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(ignore_file_path)], check=True)
                else:
                    subprocess.run(["xdg-open", str(ignore_file_path)], check=True)
            except Exception as e_os:
                logger.error(f"모든 자동 열기 시도 실패: {e_os}", exc_info=True)
                typer.secho("편집기를 자동으로 열 수 없습니다.", fg=typer.colors.YELLOW)
                typer.echo(f"아래 경로의 파일을 직접 열어주세요:\n{ignore_file_path}")

    except Exception as e:
        logger.error(f".pagrignore 명령어 처리 중 오류 발생: {e}", exc_info=True)
        typer.secho(f".pagrignore 처리 중 오류 발생: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()