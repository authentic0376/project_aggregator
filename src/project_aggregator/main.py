# src/project_aggregator/main.py
import typer
from pathlib import Path
from typing_extensions import Annotated
import sys
import os
from platformdirs import user_downloads_dir
import subprocess
from typing import Optional, List
import logging

# 로깅 설정 로더 임포트 및 설정 적용
from .logging_config import setup_logging
setup_logging()

# 로거 인스턴스 가져오기 (main 모듈용)
logger = logging.getLogger(__name__)

# logic 모듈의 함수들을 가져옵니다.
from .logic import (
    load_combined_ignore_spec,
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
    __version__ = "0.2.0"  # fallback

# --- Typer 앱 생성 및 기본 설정 ---
app = typer.Typer(
    name="pagr",
    help="프로젝트의 파일 구조와 코드를 하나의 텍스트 파일로 취합합니다.",
    add_completion=False,
    no_args_is_help=True,
)

# --- 공통 옵션 ---
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
    help="루트 디렉토리 내에서 포함할 파일/폴더의 Glob 패턴. 생략 시 무시된 파일을 제외한 모든 파일이 대상이 됩니다.",
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

# --- 'run' 명령어 ---
@app.command()
def run(
        include_patterns: IncludePatternsArgument = None,
        root_path: RootPathOption = None,
        output_path: OutputPathOption = None,
):
    """
    프로젝트 파일을 취합하여 저장합니다. (.gitignore, .pagrignore 규칙 적용)
    """
    logger.info("'run' 명령어를 시작합니다.")
    try:
        effective_root_dir = root_path if root_path else Path.cwd()
        logger.debug(f"적용된 루트 디렉토리: {effective_root_dir}")
        typer.echo(f"루트 디렉토리: {effective_root_dir}")
        if include_patterns:
            typer.echo(f"포함할 파일 패턴 (인자): {', '.join(include_patterns)}")

        combined_ignore_spec = load_combined_ignore_spec(effective_root_dir)

        logger.info("프로젝트 파일 스캔 중...")
        relative_code_paths = scan_and_filter_files(
            effective_root_dir,
            combined_ignore_spec,
            include_patterns
        )
        logger.info(f"스캔 완료. {len(relative_code_paths)}개의 파일을 취합 대상으로 찾았습니다.")

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
            typer.secho("경고: 취합할 파일이 없습니다. (지정한 패턴과 일치하는 파일이 없거나 모두 무시되었습니다)", fg=typer.colors.YELLOW, err=True)

        logger.info("디렉토리 트리 생성 중...")
        tree_output = generate_tree(effective_root_dir, combined_ignore_spec)

        logger.info(f"{len(relative_code_paths)}개 파일의 내용 취합 중...")
        code_output = aggregate_codes(effective_root_dir, relative_code_paths) if relative_code_paths else "[취합 대상으로 선택된 파일이 없습니다]"

        included_display = '인자로 주어진 패턴' if include_patterns else '모든 비-무시 파일'

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
            f"      (Included: {included_display})\n"
            f"========================================\n\n"
            f"{code_output}\n"
        )

        logger.info(f"{output_path}에 결과 저장 중...")
        output_path.write_text(final_output, encoding='utf-8')
        typer.secho(f"성공적으로 파일을 생성했습니다: {output_path}", fg=typer.colors.GREEN)

    except typer.Exit:
        raise
    except Exception as e:
        logger.critical(f"'run' 명령어 실행 중 예상치 못한 오류 발생: {e}", exc_info=True)
        typer.secho(f"예상치 못한 오류가 발생했습니다: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

# --- 'preview' 명령어 ---
@app.command()
def preview(
        include_patterns: IncludePatternsArgument = None,
        root_path: RootPathOption = None,
        max_files: Annotated[int, typer.Option("--max-files", help="각 디렉토리마다 표시할 최대 파일 수.")] = 10,
):
    """
    'run' 실행 시 어떤 파일들이 취합될지 미리 봅니다.
    """
    logger.info("'preview' 명령어를 시작합니다.")
    try:
        effective_root_dir = root_path if root_path else Path.cwd()
        logger.debug(f"적용된 루트 디렉토리: {effective_root_dir}")

        combined_ignore_spec = load_combined_ignore_spec(effective_root_dir)

        logger.info("미리보기를 위해 프로젝트 파일 스캔 중...")
        relative_code_paths = scan_and_filter_files(
            effective_root_dir,
            combined_ignore_spec,
            include_patterns
        )

        typer.secho(f"\n[미리보기] 총 {len(relative_code_paths)}개의 파일이 취합 대상입니다.", fg=typer.colors.CYAN, bold=True)
        inclusion_tree = generate_inclusion_tree(
            effective_root_dir,
            relative_code_paths,
            max_files_per_dir=max_files
        )
        typer.echo(inclusion_tree)

    except Exception as e:
        logger.error(f"'preview' 실행 중 예기치 않은 오류 발생: {e}", exc_info=True)
        typer.secho(f"미리보기 중 오류가 발생했습니다: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# 'ignore' 명령어에 대한 기본 내용
DEFAULT_PAGRIGNORE_CONTENT = """\
# pagr이 항상 무시할 패턴을 추가합니다. .gitignore와 유사하게 동작합니다.
# 여기에 작성된 규칙은 .gitignore 규칙 이후에 적용됩니다.
#
# '!' 접두사를 사용하여 무시 규칙을 재정의할 수 있습니다.
# 예를 들어, .gitignore에서 'logs/'를 무시하더라도, 여기서 '!logs/important.log'를
# 추가하면 해당 파일은 취합 대상에 포함됩니다.
#
# --- 예시 ---
# build/
# dist/
#
# # 'dist' 폴더 내의 특정 파일만 예외적으로 포함
# !dist/critical.js

*.pyc
.venv/
.idea/
"""

@app.command()
def ignore():
    """
    pagr 전용 무시 규칙 파일(.pagrignore)을 열거나 생성합니다.
    """
    ignore_file_path = Path.cwd() / ".pagrignore"
    logger.info(f"'ignore' 명령어를 실행합니다: {ignore_file_path}")

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
                logger.error(f"편집기 자동 열기 실패: {e_os}", exc_info=True)
                typer.secho("편집기를 자동으로 열 수 없습니다.", fg=typer.colors.YELLOW)
                typer.echo(f"아래 경로의 파일을 직접 열어주세요:\n{ignore_file_path}")

    except Exception as e:
        logger.error(f".pagrignore 처리 중 오류 발생: {e}", exc_info=True)
        typer.secho(f".pagrignore 처리 중 오류 발생: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()