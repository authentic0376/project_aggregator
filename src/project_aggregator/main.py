# src/project_aggregator/main.py
import typer
from pathlib import Path
from typing_extensions import Annotated
import sys
import os
from platformdirs import user_downloads_dir # 다운로드 폴더 경로용
import subprocess # 편집기 실행 대안 (typer.launch가 안될 경우)
from typing import Optional
import logging # 로깅 모듈 임포트

# 로깅 설정 로더 임포트 및 설정 적용
# 앱 시작 시 로깅 설정을 가장 먼저 적용하는 것이 좋습니다.
from .logging_config import setup_logging
setup_logging()

# 로거 인스턴스 가져오기 (main 모듈용)
# __name__을 사용하면 로거 이름이 'project_aggregator.main'이 됩니다.
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
    __version__ = "0.1.0" # fallback

# --- Typer 앱 생성 및 기본 설정 ---
app = typer.Typer(
    name="pagr", # 명령어 이름 설정
    help="Aggregates project files into a single text file, respecting .gitignore and .pagrignore.",
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
    pass # 콜백은 실제 로직을 수행하지 않음

# --- 'run' 하위 명령어 ---
@app.command()
def run(
    input_path: Annotated[Path, typer.Argument(
        help="Path to the project directory to aggregate.",
        exists=True,
        file_okay=False, # 디렉토리여야 함
        dir_okay=True,
        readable=True,
        resolve_path=True, # 절대 경로로 변환
    )] = Path.cwd(), # 기본값: 현재 작업 디렉토리

    output_path: Annotated[Optional[Path], typer.Option(
        "--output", "-o",
        help="Path to the output text file. Defaults to 'pagr_output.txt' in the Downloads folder.",
        resolve_path=True, # 절대 경로로 변환
    )] = None, # 기본값은 아래에서 설정
):
    """
    Generates a directory tree and aggregates code files from the input path.
    Excludes files based on .gitignore and .pagrignore rules.
    """
    logger.info(f"Starting 'run' command.")
    logger.debug(f"Input path received: {input_path}")
    logger.debug(f"Output path option initially: {output_path}")

    # --- 1. 출력 경로 기본값 설정 ---
    if output_path is None:
        try:
            downloads_dir = Path(user_downloads_dir())
            # 다운로드 디렉토리 존재 여부 확인 및 필요시 생성 (선택적이지만 권장)
            if not downloads_dir.exists():
                 logger.info(f"Downloads directory not found at {downloads_dir}, attempting to create it.")
                 try:
                      downloads_dir.mkdir(parents=True, exist_ok=True)
                      logger.info(f"Successfully created downloads directory: {downloads_dir}")
                 except Exception as mkdir_e:
                      logger.warning(f"Could not create downloads directory {downloads_dir}: {mkdir_e}. Falling back to current directory.", exc_info=True)
                      output_path = Path.cwd() / "pagr_output.txt"
            else:
                 output_path = downloads_dir / "pagr_output.txt"
            logger.debug(f"Default output path determined: {output_path}")

        except Exception as e: # user_downloads_dir() 실패 또는 다른 예외
            # typer.secho 대신 logger.warning 사용
            logger.warning(f"Could not determine or use Downloads directory ({e}). Using current directory for output.", exc_info=False) # 스택 트레이스 제외 가능
            output_path = Path.cwd() / "pagr_output.txt"
            logger.debug(f"Output path set to current directory fallback: {output_path}")
    else:
        # 사용자가 명시적으로 output_path를 제공한 경우 로깅
        logger.debug(f"Using user-provided output path: {output_path}")

    # 사용자에게 중요한 정보는 typer.echo로 계속 표시
    typer.echo(f"Input project directory: {input_path}")
    typer.echo(f"Output file path: {output_path}")

    try:
        # --- 2. Ignore 규칙 로드 ---
        # 진행 상황 로깅
        logger.info("Loading ignore rules (.gitignore, .pagrignore)...")
        # input_path 기준으로 ignore 파일 검색
        combined_ignore_spec = load_combined_ignore_spec(input_path)
        logger.debug("Ignore rules loaded.")

        # --- 3. 파일 스캔 및 필터링 ---
        logger.info("Scanning project files...")
        relative_code_paths = scan_and_filter_files(input_path, combined_ignore_spec)
        logger.info(f"Scan complete. Found {len(relative_code_paths)} files to include.")

        if not relative_code_paths:
             # 경고는 logger와 사용자 출력 모두 사용 가능
             logger.warning("No files found to aggregate after applying ignore rules.")
             typer.secho("Warning: No files found to aggregate after applying ignore rules.", fg=typer.colors.YELLOW, err=True)
             # 결과 파일은 생성하되 내용은 비어있도록 계속 진행

        # --- 4. 디렉토리 트리 생성 ---
        logger.info("Generating directory tree...")
        tree_output = generate_tree(input_path, combined_ignore_spec)
        logger.debug("Directory tree generated.")

        # --- 5. 코드 취합 ---
        if relative_code_paths:
             logger.info(f"Aggregating content of {len(relative_code_paths)} file(s)...")
             code_output = aggregate_codes(input_path, relative_code_paths)
             logger.debug("Code aggregation complete.")
        else:
             logger.info("Skipping code aggregation as no files were found.")
             code_output = "[No files to aggregate based on ignore rules]" # 결과 파일에 표시될 내용

        # --- 6. 최종 결과 조합 ---
        logger.debug("Combining tree and aggregated code into final output string.")
        final_output = (
            "========================================\n"
            "        Project Directory Tree\n"
            "========================================\n\n"
            f"{tree_output}\n\n\n"
            "========================================\n"
            "          Aggregated Code Files\n"
            "========================================\n\n"
            f"{code_output}\n"
        )
        logger.debug("Final output string created.")

        # --- 7. 파일 쓰기 ---
        logger.info(f"Writing output to: {output_path} ...")
        try:
            # 출력 디렉토리가 없을 경우 생성 (output_path가 파일명을 포함하므로 parent 사용)
            output_dir = output_path.parent
            if not output_dir.exists():
                logger.info(f"Output directory {output_dir} does not exist. Creating...")
                output_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Output directory {output_dir} created.")

            output_path.write_text(final_output, encoding='utf-8')
            # 성공 메시지는 사용자에게 명확히 보여주는 것이 좋음
            typer.secho(f"Successfully generated output to {output_path}", fg=typer.colors.GREEN)
            logger.info(f"Output successfully written to {output_path}")
        except Exception as e:
             # 파일 쓰기 실패 시 에러 로깅 (스택 트레이스 포함) 및 사용자 알림
             logger.error(f"Error writing output file {output_path}: {e}", exc_info=True)
             typer.secho(f"Error writing output file {output_path}: {e}", fg=typer.colors.RED, err=True)
             raise typer.Exit(code=2) # 에러 코드와 함께 종료

    # 예외 처리: 각 에러 타입에 대해 로깅 및 사용자 알림
    except FileNotFoundError as e:
         logger.error(f"Error: Input path or a required file not found: {e}", exc_info=True) # 스택 트레이스 포함 가능
         typer.secho(f"Error: Input path or a required file not found: {e}", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)
    except PermissionError as e:
         logger.error(f"Error: Permission denied accessing path or file: {e}", exc_info=True) # 스택 트레이스 포함 가능
         typer.secho(f"Error: Permission denied accessing path or file: {e}", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)
    except Exception as e:
        # 예상치 못한 모든 오류 처리
        logger.critical(f"An unexpected error occurred during 'run' command: {e}", exc_info=True) # 스택 트레이스 필수
        typer.secho(f"An unexpected error occurred during run: {e}", fg=typer.colors.RED, err=True)
        # traceback.print_exc()는 logger가 처리하므로 제거
        raise typer.Exit(code=3) # 다른 에러 코드 사용


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
                ignore_file_path.touch() # 빈 파일 생성
                # 사용자 알림
                typer.secho(f"Created empty '{ignore_file_path.name}' in the current directory.", fg=typer.colors.GREEN)
                logger.info(f"Successfully created '{ignore_file_path.name}'.")
            except Exception as touch_e:
                logger.error(f"Failed to create {ignore_file_path}: {touch_e}", exc_info=True)
                typer.secho(f"Error: Could not create file {ignore_file_path.name}: {touch_e}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
        else:
            logger.debug(f"'{ignore_file_path.name}' already exists at {ignore_file_path}.")

        # 사용자 알림
        typer.echo(f"Attempting to open '{ignore_file_path.name}' in your default editor...")
        logger.info(f"Attempting to open '{ignore_file_path.name}' in default editor...")

        # typer.launch() 사용 시도
        try:
             typer.launch(str(ignore_file_path), locate=False)
             typer.echo("Default editor launched (via typer.launch). Please edit and save the file.")
             logger.info("Editor launched successfully using typer.launch.")
        except Exception as e_launch: # typer.launch 실패 시 대체 방법 시도
             logger.warning(f"typer.launch failed: {e_launch}. Trying system-specific methods...", exc_info=False)
             typer.secho(f"typer.launch failed: {e_launch}. Trying system default methods...", fg=typer.colors.YELLOW, err=True)

             editor_launched = False
             # 환경 변수 EDITOR 확인
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

             # 플랫폼별 기본 방법 시도 (EDITOR 없거나 실패 시)
             if not editor_launched:
                 logger.debug(f"Trying platform-specific open command. Platform: {sys.platform}")
                 try:
                     if sys.platform == "win32":
                         os.startfile(str(ignore_file_path))
                         logger.info("Opened file using os.startfile on Windows.")
                         typer.echo("Opened file with associated program on Windows.")
                         editor_launched = True
                     elif sys.platform == "darwin": # macOS
                         subprocess.run(["open", str(ignore_file_path)], check=True)
                         logger.info("Opened file using 'open' command on macOS.")
                         typer.echo("Opened file with 'open' command on macOS.")
                         editor_launched = True
                     else: # Linux 등 다른 유닉스 계열
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

             # 모든 방법 실패 시 사용자에게 수동으로 열도록 안내
             if not editor_launched:
                  logger.warning("All attempts to open the editor automatically failed.")
                  typer.echo("Could not automatically open the editor.")
                  typer.echo(f"Please open the file manually: {ignore_file_path}")


    except Exception as e:
        # 'ignore' 명령어 처리 중 예상치 못한 오류
        logger.error(f"An error occurred processing .pagrignore command: {e}", exc_info=True)
        typer.secho(f"An error occurred processing .pagrignore: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- 스크립트로 직접 실행될 때 app 실행 ---
if __name__ == "__main__":
    # 로깅 설정은 모듈 상단에서 이미 호출됨
    # setup_logging()
    logger.debug("Running application directly via __main__.")
    app()