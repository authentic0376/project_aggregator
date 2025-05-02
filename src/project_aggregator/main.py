# src/project_aggregator/main.py
import typer
from pathlib import Path
from typing_extensions import Annotated
import sys
import os
from platformdirs import user_downloads_dir # 다운로드 폴더 경로용
import subprocess # 편집기 실행 대안 (typer.launch가 안될 경우)
from typing import Optional, List # List 추가
import logging # 로깅 모듈 임포트

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
    aggregate_codes,
)

# 버전 정보 가져오기
try:
    from importlib.metadata import version
    __version__ = version("project_aggregator")
except ImportError:
    __version__ = "0.1.1" # fallback (pyproject.toml 버전과 일치)

# --- Typer 앱 생성 및 기본 설정 ---
app = typer.Typer(
    name="pagr", # 명령어 이름 설정
    help="Aggregates project files into a single text file, respecting .gitignore, .pagrignore and optional include patterns.",
    add_completion=False,
    no_args_is_help=True, # 인자 없이 실행 시 도움말 표시
)

# --- 버전 콜백 함수 ---
def version_callback(value: bool):
    if value:
        typer.echo(f"pagr version: {__version__}") # 버전 표시는 사용자 출력 유지
        raise typer.Exit()

# --- 전역 옵션: 버전 ---
@app.callback()
def main_options(
    version: Annotated[Optional[bool], typer.Option(
        "--version", "-v",
        help="Show the application's version and exit.",
        callback=version_callback,
        is_eager=True # 다른 옵션/명령보다 먼저 처리
    )] = None,
):
    """
    pagr: A tool to aggregate project files.
    """
    pass

# --- 'run' 하위 명령어 ---
@app.command()
def run(
    # 위치 인자: 포함할 상대 경로/패턴 (옵션)
    include_patterns: Annotated[Optional[List[str]], typer.Argument(
        help="Optional relative paths or glob patterns to include within the root directory. If omitted, all non-ignored files under the root are included.",
        show_default=False, # 기본값 (None)은 도움말에 명시하지 않음
    )] = None,

    # 옵션: 루트 디렉토리 지정
    root_path: Annotated[Optional[Path], typer.Option(
        "--root", "-r",
        help="Root directory to aggregate. Defaults to the current working directory.",
        exists=True,      # 경로가 존재해야 함
        file_okay=False,  # 파일은 안 됨
        dir_okay=True,    # 디렉토리여야 함
        readable=True,    # 읽기 가능해야 함
        resolve_path=True,# 절대 경로로 변환
        show_default=False,# 기본값은 도움말에 명시하지 않음 (아래 로직에서 처리)
    )] = None,

    # 옵션: 출력 파일 경로
    output_path: Annotated[Optional[Path], typer.Option(
        "--output", "-o",
        help="Path to the output text file. Defaults to 'pagr_output.txt' in the Downloads folder.",
        resolve_path=True, # 절대 경로로 변환
        # writable=True, # Typer 0.12+ 에서 사용 가능 (쓰기 가능 여부 체크)
        dir_okay=False,   # 디렉토리는 안 됨
        file_okay=True,   # 파일이어야 함
    )] = None, # 기본값은 아래에서 설정
):
    """
    Generates a directory tree and aggregates specific code files.

    - Aggregation starts from the ROOT directory (current dir or --root).
    - Files/directories matching patterns in .gitignore/.pagrignore are excluded.
    - If INCLUDE_PATTERNS are given, only files matching these patterns (relative to ROOT)
      AND not ignored will be included in the aggregated code section.
    - The directory tree shows the structure respecting ignore rules, but not
      necessarily filtered by INCLUDE_PATTERNS.
    """
    logger.info(f"Starting 'run' command.")

    # --- 1. 루트 경로 결정 ---
    effective_root_dir = root_path if root_path else Path.cwd()
    logger.debug(f"Effective root directory set to: {effective_root_dir}")
    if root_path:
        logger.debug(f"Root directory explicitly provided via --root: {root_path}")
    else:
        logger.debug("Using current working directory as root (no --root specified).")

    # --- 2. 포함 패턴 로깅 ---
    if include_patterns:
        logger.debug(f"Include patterns received: {include_patterns}")
    else:
        logger.debug("No include patterns specified. Will include all non-ignored files.")

    # --- 3. 출력 경로 설정 ---
    logger.debug(f"Output path option initially: {output_path}")
    if output_path is None:
        try:
            downloads_dir = Path(user_downloads_dir())
            if not downloads_dir.exists():
                 logger.info(f"Downloads directory not found at {downloads_dir}, attempting to create it.")
                 try:
                      downloads_dir.mkdir(parents=True, exist_ok=True)
                      logger.info(f"Successfully created downloads directory: {downloads_dir}")
                 except Exception as mkdir_e:
                      logger.warning(f"Could not create downloads directory {downloads_dir}: {mkdir_e}. Falling back to current directory for output.", exc_info=True)
                      output_path = Path.cwd() / "pagr_output.txt"
            else:
                 output_path = downloads_dir / "pagr_output.txt"
            logger.debug(f"Default output path determined: {output_path}")
        except Exception as e:
            logger.warning(f"Could not determine or use Downloads directory ({e}). Using current directory for output.", exc_info=False)
            output_path = Path.cwd() / "pagr_output.txt"
            logger.debug(f"Output path set to current directory fallback: {output_path}")
    else:
        # 사용자가 명시적으로 output_path를 제공한 경우 부모 디렉토리 확인/생성 필요
        output_parent_dir = output_path.parent
        if not output_parent_dir.exists():
            logger.info(f"Parent directory for specified output path does not exist: {output_parent_dir}. Attempting to create.")
            try:
                output_parent_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Successfully created output parent directory: {output_parent_dir}")
            except Exception as mkdir_e:
                 logger.error(f"Could not create parent directory {output_parent_dir} for output file: {mkdir_e}", exc_info=True)
                 typer.secho(f"Error: Could not create directory {output_parent_dir} for output file.", fg=typer.colors.RED, err=True)
                 raise typer.Exit(code=1)
        logger.debug(f"Using user-provided output path: {output_path}")

    # 사용자에게 최종 경로 정보 표시
    typer.echo(f"Root directory: {effective_root_dir}")
    if include_patterns:
        typer.echo(f"Including files matching: {', '.join(include_patterns)}")
    typer.echo(f"Output file: {output_path}")

    try:
        # --- 4. Ignore 규칙 로드 ---
        logger.info("Loading ignore rules (.gitignore, .pagrignore)...")
        combined_ignore_spec = load_combined_ignore_spec(effective_root_dir)
        logger.debug("Ignore rules loaded.")

        # --- 5. 파일 스캔 및 필터링 (이제 include_patterns 전달) ---
        logger.info("Scanning project files...")
        relative_code_paths = scan_and_filter_files(
            effective_root_dir,
            combined_ignore_spec,
            include_patterns # 전달
        )
        if include_patterns:
             logger.info(f"Scan complete. Found {len(relative_code_paths)} files matching include patterns and not ignored.")
             if not relative_code_paths:
                  typer.secho("Warning: No files matched the specified include patterns after applying ignore rules.", fg=typer.colors.YELLOW, err=True)
        else:
             logger.info(f"Scan complete. Found {len(relative_code_paths)} files to include (all non-ignored files).")
             if not relative_code_paths:
                  typer.secho("Warning: No files found to aggregate after applying ignore rules.", fg=typer.colors.YELLOW, err=True)

        # --- 6. 디렉토리 트리 생성 (Ignore 규칙만 적용) ---
        logger.info("Generating directory tree (based on ignore rules)...")
        tree_output = generate_tree(effective_root_dir, combined_ignore_spec)
        logger.debug("Directory tree generated.")

        # --- 7. 코드 취합 ---
        if relative_code_paths:
             logger.info(f"Aggregating content of {len(relative_code_paths)} file(s)...")
             code_output = aggregate_codes(effective_root_dir, relative_code_paths)
             logger.debug("Code aggregation complete.")
        else:
             logger.info("Skipping code aggregation as no files were selected.")
             code_output = "[No files selected for aggregation based on include/ignore rules]"

        # --- 8. 최종 결과 조합 ---
        logger.debug("Combining tree and aggregated code into final output string.")
        final_output = (
            "========================================\n"
            f" Project Root: {effective_root_dir}\n" # 루트 경로 명시 추가
            "========================================\n\n"
            "========================================\n"
            "        Project Directory Tree\n"
            "    (Ignoring .git, .gitignore, .pagrignore)\n" # 트리 필터링 기준 명시
            "========================================\n\n"
            f"{tree_output}\n\n\n"
            "========================================\n"
            "          Aggregated Code Files\n"
            f"   (Included: {', '.join(include_patterns) if include_patterns else 'All non-ignored files'})\n" # 포함 기준 명시
            "========================================\n\n"
            f"{code_output}\n"
        )
        logger.debug("Final output string created.")

        # --- 9. 파일 쓰기 ---
        logger.info(f"Writing output to: {output_path} ...")
        try:
            # 출력 디렉토리는 위에서 이미 확인/생성 시도됨
            output_path.write_text(final_output, encoding='utf-8')
            typer.secho(f"Successfully generated output to {output_path}", fg=typer.colors.GREEN)
            logger.info(f"Output successfully written to {output_path}")
        except Exception as e:
             logger.error(f"Error writing output file {output_path}: {e}", exc_info=True)
             typer.secho(f"Error writing output file {output_path}: {e}", fg=typer.colors.RED, err=True)
             raise typer.Exit(code=2)

    except FileNotFoundError as e:
         logger.error(f"Error: Input path or a required file not found: {e}", exc_info=True)
         typer.secho(f"Error: Input path or a required file not found: {e}", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)
    except PermissionError as e:
         logger.error(f"Error: Permission denied accessing path or file: {e}", exc_info=True)
         typer.secho(f"Error: Permission denied accessing path or file: {e}", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred during 'run' command: {e}", exc_info=True)
        typer.secho(f"An unexpected error occurred during run: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=3)


# --- 'ignore' 하위 명령어 ---
@app.command()
def ignore():
    """
    Opens the .pagrignore file in the current directory for editing.
    Creates the file if it doesn't exist.
    """
    ignore_file_path = Path.cwd() / ".pagrignore"
    logger.info(f"Executing 'ignore' command for path: {ignore_file_path}")

    try:
        if not ignore_file_path.exists():
            logger.info(f"'{ignore_file_path.name}' not found at {ignore_file_path}. Creating empty file...")
            try:
                ignore_file_path.touch()
                typer.secho(f"Created empty '{ignore_file_path.name}' in the current directory.", fg=typer.colors.GREEN)
                logger.info(f"Successfully created '{ignore_file_path.name}'.")
            except Exception as touch_e:
                logger.error(f"Failed to create {ignore_file_path}: {touch_e}", exc_info=True)
                typer.secho(f"Error: Could not create file {ignore_file_path.name}: {touch_e}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
        else:
            logger.debug(f"'{ignore_file_path.name}' already exists at {ignore_file_path}.")

        typer.echo(f"Attempting to open '{ignore_file_path.name}' in your default editor...")
        logger.info(f"Attempting to open '{ignore_file_path.name}' in default editor...")

        try:
             typer.launch(str(ignore_file_path), locate=False)
             typer.echo("Default editor launched (via typer.launch). Please edit and save the file.")
             logger.info("Editor launched successfully using typer.launch.")
        except Exception as e_launch:
             logger.warning(f"typer.launch failed: {e_launch}. Trying system-specific methods...", exc_info=False)
             typer.secho(f"typer.launch failed: {e_launch}. Trying system default methods...", fg=typer.colors.YELLOW, err=True)

             editor_launched = False
             editor = os.environ.get('EDITOR')
             if editor:
                 logger.debug(f"Trying editor from EDITOR environment variable: {editor}")
                 try:
                    subprocess.run([editor, str(ignore_file_path)], check=True)
                    typer.echo(f"Editor '{editor}' launched. Please edit and save the file.")
                    logger.info(f"Editor launched successfully using EDITOR variable: {editor}")
                    editor_launched = True
                 except Exception as e_sub:
                     logger.error(f"Failed to launch editor using EDITOR variable ('{editor}'): {e_sub}", exc_info=True)
                     typer.secho(f"Failed to launch editor using EDITOR ('{editor}'): {e_sub}", fg=typer.colors.RED, err=True)

             if not editor_launched:
                 logger.debug(f"Trying platform-specific open command. Platform: {sys.platform}")
                 try:
                     if sys.platform == "win32":
                         os.startfile(str(ignore_file_path))
                         logger.info("Opened file using os.startfile on Windows.")
                         typer.echo("Opened file with associated program on Windows.")
                         editor_launched = True
                     elif sys.platform == "darwin":
                         subprocess.run(["open", str(ignore_file_path)], check=True)
                         logger.info("Opened file using 'open' command on macOS.")
                         typer.echo("Opened file with 'open' command on macOS.")
                         editor_launched = True
                     else:
                         subprocess.run(["xdg-open", str(ignore_file_path)], check=True)
                         logger.info("Opened file using 'xdg-open'.")
                         typer.echo("Opened file using 'xdg-open'.")
                         editor_launched = True
                 except FileNotFoundError:
                     cmd = "startfile" if sys.platform == "win32" else "open" if sys.platform == "darwin" else "xdg-open"
                     logger.error(f"Command '{cmd}' not found. Cannot open file automatically.", exc_info=False)
                     typer.secho(f"Error: Could not find command ('{cmd}') to open the file automatically.", fg=typer.colors.RED, err=True)
                 except Exception as e_os:
                     cmd = "startfile" if sys.platform == "win32" else "open" if sys.platform == "darwin" else "xdg-open"
                     logger.error(f"Failed to open file using '{cmd}': {e_os}", exc_info=True)
                     typer.secho(f"Failed to open file using system default: {e_os}", fg=typer.colors.RED, err=True)

             if not editor_launched:
                  logger.warning("All attempts to open the editor automatically failed.")
                  typer.echo("Could not automatically open the editor.")
                  typer.echo(f"Please open the file manually: {ignore_file_path}")


    except Exception as e:
        logger.error(f"An error occurred processing .pagrignore command: {e}", exc_info=True)
        typer.secho(f"An error occurred processing .pagrignore: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- 스크립트로 직접 실행될 때 app 실행 ---
if __name__ == "__main__":
    logger.debug("Running application directly via __main__.")
    app()