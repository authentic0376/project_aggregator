# src/project_aggregator/main.py
import typer
from pathlib import Path
from typing_extensions import Annotated
import sys
import os
from platformdirs import user_downloads_dir # 다운로드 폴더 경로용
import subprocess # 편집기 실행 대안 (typer.launch가 안될 경우)
from typing import Optional

# logic 모듈의 함수들을 가져옵니다.
from .logic import (
    load_combined_ignore_spec,
    scan_and_filter_files,
    generate_tree,
    aggregate_codes,
)

# 버전 정보 가져오기 (pyproject.toml에서 읽어오는 것이 이상적이지만 여기선 하드코딩 또는 __version__ 사용)
try:
    from importlib.metadata import version
    __version__ = version("project_aggregator")
except ImportError:
    # Python 3.7 등 importlib.metadata가 없는 경우 (여기선 3.12 이상이므로 필요 없을 수 있음)
    # 또는 패키지가 설치되지 않은 상태일 때 대비
    __version__ = "0.1.0" # pyproject.toml과 일치시키세요


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
        typer.echo(f"pagr version: {__version__}")
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
    # --- 1. 출력 경로 기본값 설정 ---
    if output_path is None:
        try:
            downloads_dir = Path(user_downloads_dir())
            # 다운로드 디렉토리가 없으면 생성 시도 (선택적)
            # downloads_dir.mkdir(parents=True, exist_ok=True)
            output_path = downloads_dir / "pagr_output.txt"
        except Exception as e: # user_downloads_dir() 실패 시 현재 디렉토리에 저장
            typer.secho(f"Warning: Could not determine Downloads directory ({e}). Using current directory for output.", fg=typer.colors.YELLOW, err=True)
            output_path = Path.cwd() / "pagr_output.txt"

    typer.echo(f"Input project directory: {input_path}")
    typer.echo(f"Output file path: {output_path}")

    try:
        # --- 2. Ignore 규칙 로드 ---
        typer.echo("Loading ignore rules (.gitignore, .pagrignore)...")
        # input_path 기준으로 ignore 파일 검색
        combined_ignore_spec = load_combined_ignore_spec(input_path)

        # --- 3. 파일 스캔 및 필터링 ---
        typer.echo("Scanning project files...")
        relative_code_paths = scan_and_filter_files(input_path, combined_ignore_spec)

        if not relative_code_paths:
             typer.secho("Warning: No files found to aggregate after applying ignore rules.", fg=typer.colors.YELLOW, err=True)
             # 결과 파일은 생성하되 내용은 비어있도록 진행할 수 있음
             # 또는 여기서 종료할 수도 있음 typer.Exit()

        # --- 4. 디렉토리 트리 생성 ---
        typer.echo("Generating directory tree...")
        # generate_tree는 필터링된 파일 목록이 아니라, 디렉토리 구조를 보여주기 위해
        # ignore spec을 직접 사용해야 함
        tree_output = generate_tree(input_path, combined_ignore_spec)

        # --- 5. 코드 취합 ---
        if relative_code_paths:
             typer.echo(f"Aggregating {len(relative_code_paths)} file(s)...")
             code_output = aggregate_codes(input_path, relative_code_paths)
        else:
             code_output = "[No files to aggregate based on ignore rules]"

        # --- 6. 최종 결과 조합 ---
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

        # --- 7. 파일 쓰기 ---
        typer.echo(f"Writing output to: {output_path} ...")
        try:
            # 출력 디렉토리가 없을 경우 생성
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(final_output, encoding='utf-8')
            typer.secho(f"Successfully generated output to {output_path}", fg=typer.colors.GREEN)
        except Exception as e:
             typer.secho(f"Error writing output file {output_path}: {e}", fg=typer.colors.RED, err=True)
             raise typer.Exit(code=2)

    except FileNotFoundError as e:
         typer.secho(f"Error: Input path or a required file not found: {e}", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)
    except PermissionError as e:
         typer.secho(f"Error: Permission denied accessing path or file: {e}", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during run: {e}", fg=typer.colors.RED, err=True)
        import traceback
        traceback.print_exc() # 개발/디버깅 시 상세 오류 출력
        raise typer.Exit(code=3)


# --- 'ignore' 하위 명령어 ---
@app.command()
def ignore():
    """
    Opens the .pagrignore file in the current directory for editing.
    Creates the file if it doesn't exist.
    """
    ignore_file_path = Path.cwd() / ".pagrignore"
    typer.echo(f"Checking for {ignore_file_path}...")

    try:
        if not ignore_file_path.exists():
            typer.echo(f"'{ignore_file_path.name}' not found. Creating empty file...")
            ignore_file_path.touch() # 빈 파일 생성
            typer.secho(f"Created '{ignore_file_path.name}'.", fg=typer.colors.GREEN)

        typer.echo(f"Attempting to open '{ignore_file_path.name}' in your default editor...")

        # typer.launch() 사용 (더 간단하고 플랫폼 독립적 시도)
        try:
             typer.launch(str(ignore_file_path), locate=False) # locate=False 는 파일 자체를 열려고 시도
             typer.echo("Editor launched. Please edit and save the file.")
        except Exception as e_launch: # typer.launch 실패 시 대체 방법 시도
             typer.secho(f"typer.launch failed: {e_launch}. Trying system default...", fg=typer.colors.YELLOW, err=True)

             # 대체: click.edit() (click 의존성 추가 필요) 또는 os/subprocess 사용
             # os.system 사용 (간단하지만 보안 위험 가능성 및 플랫폼 의존성)
             # editor = os.environ.get('EDITOR', 'vim' if sys.platform != 'win32' else 'notepad')
             # os.system(f"{editor} \"{ignore_file_path}\"")

             # subprocess 사용 (조금 더 안전)
             editor = os.environ.get('EDITOR')
             if editor:
                 try:
                    subprocess.run([editor, str(ignore_file_path)], check=True)
                    typer.echo("Editor launched using EDITOR variable.")
                 except Exception as e_sub:
                     typer.secho(f"Failed to launch editor using EDITOR ({editor}): {e_sub}", fg=typer.colors.RED, err=True)
                     typer.echo("Please open the file manually.")
             elif sys.platform == "win32":
                 try:
                     os.startfile(str(ignore_file_path)) # Windows에서 파일 연결된 프로그램 실행
                     typer.echo("Opened file with associated program on Windows.")
                 except Exception as e_win:
                     typer.secho(f"Failed to open file on Windows: {e_win}", fg=typer.colors.RED, err=True)
                     typer.echo("Please open the file manually.")
             elif sys.platform == "darwin": # macOS
                 try:
                     subprocess.run(["open", str(ignore_file_path)], check=True)
                     typer.echo("Opened file with 'open' command on macOS.")
                 except Exception as e_mac:
                     typer.secho(f"Failed to open file on macOS: {e_mac}", fg=typer.colors.RED, err=True)
                     typer.echo("Please open the file manually.")
             else: # Linux 등 다른 유닉스 계열
                  try:
                      subprocess.run(["xdg-open", str(ignore_file_path)], check=True)
                      typer.echo("Opened file with 'xdg-open'.")
                  except Exception as e_linux:
                      typer.secho(f"Failed to open file using 'xdg-open': {e_linux}. Is xdg-utils installed?", fg=typer.colors.RED, err=True)
                      typer.echo("Please open the file manually.")


    except Exception as e:
        typer.secho(f"An error occurred processing .pagrignore: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- 스크립트로 직접 실행될 때 app 실행 ---
if __name__ == "__main__":
    app()