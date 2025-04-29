import typer
from pathlib import Path
import yaml
from typing_extensions import Annotated
import sys
from typing import List
# pydantic 라이브러리에서 직접 ValidationError를 가져옵니다!
from pydantic import ValidationError

# 우리 모듈에서는 PathsConfig만 가져옵니다.
from .models import PathsConfig
# logic 모듈의 함수들을 가져옵니다.
from .logic import parse_gitignore, generate_tree, aggregate_codes
# Typer 애플리케이션 생성
app = typer.Typer(
    help="Generates a directory tree (respecting .gitignore) and aggregates specified code files from a project.",
    add_completion=False # 자동완성 기능 비활성화 (선택 사항)
)

def validate_paths(yaml_path: Path, root_str: str, codes_str: List[str]) -> PathsConfig:
    """
    경로 문자열을 Path 객체로 변환하고 유효성을 검사하여 PathsConfig 객체를 반환합니다.
    - root는 절대 경로로 변환합니다.
    - codes는 root 기준 상대 경로로 유지하며, 실제 파일 존재 여부를 확인합니다.
    """
    try:
        # 1. Root 경로 처리
        if not root_str:
            raise ValueError("'root' path cannot be empty.")
        # YAML 파일 위치를 기준으로 상대 경로 해석 후 절대 경로화 및 정규화
        prospective_root = (yaml_path.parent / Path(root_str)).resolve()
        if not prospective_root.is_dir():
             raise ValueError(f"Root directory does not exist or is not a directory: {prospective_root}")
        root_path = prospective_root

        # 2. Codes 경로 처리
        validated_relative_codes = []
        if not isinstance(codes_str, list):
            raise ValueError("'codes' must be a list of relative path strings.")

        for idx, p_str in enumerate(codes_str):
            if not isinstance(p_str, str) or not p_str:
                 raise ValueError(f"Item at index {idx} in 'codes' is not a valid non-empty path string.")

            # 사용자가 입력한 상대 경로 유지
            relative_code_path = Path(p_str)
            # 상대 경로가 루트 벗어나는지 체크 (예: ../../file) - 선택 사항
            # if '..' in relative_code_path.parts:
            #    raise ValueError(f"Code path '{p_str}' seems to go outside the root directory.")

            full_code_path = root_path / relative_code_path
            if not full_code_path.is_file():
                # 파일이 없으면 경고 출력하고 리스트에서 제외 (오류 대신)
                typer.secho(f"Warning: Code file not found, skipping: {full_code_path}", fg=typer.colors.YELLOW, err=True)
            else:
                # 정규화된 상대 경로 추가 (예: ./src/main.py -> src/main.py)
                # root_path 기준으로 relative_to 사용
                normalized_relative_path = full_code_path.relative_to(root_path)
                validated_relative_codes.append(normalized_relative_path)

        # 3. Pydantic 모델로 최종 생성/검증 (주로 타입 확인)
        config_data = {"root": root_path, "codes": validated_relative_codes}
        config = PathsConfig(**config_data)
        return config

    except (ValueError, ValidationError, TypeError) as e:
        # 경로 변환, 유효성 검사 오류를 BadParameter로 변환하여 Typer에게 전달
        raise typer.BadParameter(f"Configuration validation error: {e}")
    except Exception as e:
        # 기타 예상치 못한 오류
        raise typer.BadParameter(f"Unexpected error during path validation: {e}")


@app.command()
def run(
    config_path: Annotated[Path, typer.Option(
        "--config", "-c",
        help="Path to the configuration YAML file (e.g., path.yaml).",
        exists=True, # 파일 존재 여부 자동 확인
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True, # 입력 경로를 절대 경로로 자동 변환
        show_default=True, # 도움말에 기본값 표시
    )] = Path("path.yaml"), # 기본값: 현재 작업 디렉토리의 path.yaml

    output_path: Annotated[Path, typer.Option(
        "--output", "-o",
        help="Path to the output text file.",
        # writable=True, # 이 옵션은 디렉토리 권한만 체크, 파일 생성 권한은 다름. 직접 처리.
        resolve_path=True, # 입력 경로를 절대 경로로 자동 변환
        show_default=True,
    )] = Path("output.txt") # 기본값: 현재 작업 디렉토리의 output.txt
):
    """
    Reads config, generates project tree, aggregates code, and writes to output file.
    """
    try:
        # --- 1. 설정 로드 및 기본 검증 ---
        typer.echo(f"Loading configuration from: {config_path}")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                raw_config = yaml.safe_load(f)
        except Exception as e:
            raise typer.BadParameter(f"Error reading or parsing YAML file {config_path}: {e}")

        if not isinstance(raw_config, dict) or 'root' not in raw_config or 'codes' not in raw_config:
            raise typer.BadParameter(f"Invalid YAML structure in {config_path}. Must contain 'root' and 'codes' keys.")

        # --- 2. 경로 상세 검증 및 PathsConfig 생성 ---
        typer.echo("Validating paths...")
        # config_path (절대경로), raw_config['root'], raw_config['codes'] 전달
        config = validate_paths(config_path, raw_config['root'], raw_config['codes'])
        root_dir = config.root
        relative_code_paths = config.codes # 검증되고 실제 존재하는 파일 목록
        typer.echo(f"Processing project root: {root_dir}")
        if not relative_code_paths:
             typer.secho("Warning: No valid code files found to aggregate based on the config.", fg=typer.colors.YELLOW, err=True)


        # --- 3. .gitignore 파싱 ---
        gitignore_spec = parse_gitignore(root_dir)
        if gitignore_spec:
            typer.echo("Parsed .gitignore (and ignoring .git/).")
        else:
            typer.echo("No .gitignore found in root. Only ignoring .git/.")

        # --- 4. 디렉토리 트리 생성 ---
        typer.echo("Generating directory tree...")
        tree_output = generate_tree(root_dir, gitignore_spec)

        # --- 5. 코드 취합 ---
        if relative_code_paths:
             typer.echo(f"Aggregating {len(relative_code_paths)} code file(s)...")
             code_output = aggregate_codes(root_dir, relative_code_paths)
        else:
             code_output = "[No code files to aggregate]"


        # --- 6. 최종 결과 조합 ---
        final_output = (
            "========================================\n"
            "        Project Directory Tree\n"
            "========================================\n\n"
            f"{tree_output}\n\n\n" # 트리와 코드 사이 공백 추가
            "========================================\n"
            "          Aggregated Code Files\n"
            "========================================\n\n"
            f"{code_output}\n"
        )

        # --- 7. 파일 쓰기 ---
        typer.echo(f"Writing output to: {output_path} ...")
        try:
            # 출력 파일의 상위 디렉토리가 존재하지 않으면 생성
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # 파일 쓰기
            output_path.write_text(final_output, encoding='utf-8')
            typer.secho(f"Successfully generated output to {output_path}", fg=typer.colors.GREEN)
        except Exception as e:
             # 파일 쓰기 관련 오류 처리
             typer.secho(f"Error writing output file {output_path}: {e}", fg=typer.colors.RED, err=True)
             raise typer.Exit(code=2) # 파일 쓰기 오류 코드

    except typer.BadParameter as e: # 설정/검증 관련 오류 (Typer가 처리하거나 직접 발생시킨 것)
        # BadParameter는 이미 오류 메시지를 포함하므로 그대로 출력
        typer.secho(f"Configuration Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) # 설정 오류 코드
    except Exception as e: # 예상치 못한 모든 다른 오류
        typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED, err=True)
        # 디버깅을 위해 전체 traceback 출력 (개발 시 유용)
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=3) # 일반 오류 코드


# 스크립트 직접 실행 시 app 실행 (Python 표준)
if __name__ == "__main__":
    app()