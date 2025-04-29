import typer
from pathlib import Path
import yaml
from typing_extensions import Annotated
import sys
from typing import List, Set
# pydantic 라이브러리에서 직접 ValidationError를 가져옵니다!
from pydantic import ValidationError
# pathspec 가져오기
import pathspec

# 우리 모듈에서는 PathsConfig만 가져옵니다.
from .models import PathsConfig
# logic 모듈의 함수들을 가져옵니다.
# _is_relative_to 함수는 validate_paths 내에서도 사용될 수 있으므로 가져옵니다.
from .logic import parse_gitignore, generate_tree, aggregate_codes, _is_relative_to

# Typer 애플리케이션 생성
app = typer.Typer(
    help="Generates a directory tree (respecting .gitignore) and aggregates specified code files (supports glob patterns) from a project.",
    add_completion=False # 자동완성 기능 비활성화 (선택 사항)
)

# validate_paths 함수 수정: 이제 glob 패턴을 처리하고 gitignore_spec을 사용합니다.
def validate_paths(yaml_path: Path, root_str: str, codes_patterns: List[str], gitignore_spec: pathspec.PathSpec | None) -> PathsConfig:
    """
    경로 문자열(리터럴 또는 glob 패턴)을 처리하고 유효성을 검사하여 PathsConfig 객체를 반환합니다.
    - root는 절대 경로로 변환합니다.
    - codes_patterns를 해석하여 실제 파일 목록(root 기준 상대 경로)을 찾습니다.
    - .gitignore 규칙을 적용하여 찾은 파일 목록을 필터링합니다.
    """
    try:
        # 1. Root 경로 처리 (기존과 동일)
        if not root_str:
            raise ValueError("'root' path cannot be empty.")
        prospective_root = (yaml_path.parent / Path(root_str)).resolve()
        if not prospective_root.is_dir():
             raise ValueError(f"Root directory does not exist or is not a directory: {prospective_root}")
        root_path = prospective_root

        # 2. Codes 패턴 처리 및 파일 검색
        found_relative_files: Set[Path] = set() # 중복 방지를 위해 set 사용

        if not isinstance(codes_patterns, list):
            raise ValueError("'codes' must be a list of path strings or glob patterns.")

        typer.echo("Expanding code patterns and searching for files...")
        patterns_matched_any_files = False # 하나라도 파일 매칭되었는지 추적

        for idx, pattern_str in enumerate(codes_patterns):
            if not isinstance(pattern_str, str) or not pattern_str:
                 typer.secho(f"Warning: Item at index {idx} in 'codes' is not a valid non-empty string. Skipping.", fg=typer.colors.YELLOW, err=True)
                 continue

            # rglob 사용: root_path 디렉토리 내에서 패턴과 일치하는 모든 파일/디렉토리 검색
            # pattern_str 예: "src/**/*.py", "*.txt", "specific_file.py"
            matched_paths = list(root_path.rglob(pattern_str))
            pattern_matched_files_count = 0

            if not matched_paths:
                # 패턴이 아무것도 찾지 못했을 경우, 리터럴 경로인지 확인
                literal_path = root_path / Path(pattern_str)
                if literal_path.is_file():
                    matched_paths = [literal_path] # 리터럴 파일이면 처리 목록에 추가
                else:
                     typer.secho(f"Info: Pattern '{pattern_str}' did not match any files or directories.", fg=typer.colors.BLUE, err=True)


            for found_path in matched_paths:
                # rglob 결과가 파일인지 확인
                if found_path.is_file():
                    # root 기준 상대 경로 계산
                    # _is_relative_to는 안전 장치지만, rglob 특성상 거의 항상 참
                    if _is_relative_to(found_path, root_path):
                        relative_path = found_path.relative_to(root_path)

                        # .gitignore 규칙 적용
                        if gitignore_spec and gitignore_spec.match_file(str(relative_path)):
                            # typer.echo(f"  - Ignoring '{relative_path}' due to .gitignore rules.") # 디버깅용
                            continue # 무시 대상이면 건너뛰기

                        # 최종 목록에 추가 (set이므로 중복 자동 제거)
                        found_relative_files.add(relative_path)
                        pattern_matched_files_count += 1
                    else:
                        # 이론적으로 rglob 결과가 root 외부에 있을 수 없지만, 예외 처리
                         typer.secho(f"Warning: Found path {found_path} is not relative to root {root_path}. Skipping.", fg=typer.colors.YELLOW, err=True)

            if pattern_matched_files_count > 0:
                patterns_matched_any_files = True
                typer.echo(f"  - Pattern '{pattern_str}' matched {pattern_matched_files_count} file(s).")


        if not patterns_matched_any_files and codes_patterns:
             typer.secho("Warning: No files were matched by any of the provided 'codes' patterns after applying .gitignore rules.", fg=typer.colors.YELLOW, err=True)


        # 최종적으로 찾은 파일 목록을 정렬된 리스트로 변환
        validated_relative_codes = sorted(list(found_relative_files))

        # 3. Pydantic 모델로 최종 생성/검증
        config_data = {"root": root_path, "codes": validated_relative_codes}
        config = PathsConfig(**config_data)
        return config

    except (ValueError, ValidationError, TypeError) as e:
        raise typer.BadParameter(f"Configuration validation error: {e}")
    except Exception as e:
        raise typer.BadParameter(f"Unexpected error during path validation: {e}")


@app.command()
def run(
    config_path: Annotated[Path, typer.Option(
        "--config", "-c",
        help="Path to the configuration YAML file (e.g., path.yaml).",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        show_default=True,
    )] = Path("path.yaml"),

    output_path: Annotated[Path, typer.Option(
        "--output", "-o",
        help="Path to the output text file.",
        resolve_path=True,
        show_default=True,
    )] = Path("output.txt")
):
    """
    Reads config, generates project tree, aggregates code (supports glob), and writes to output file.
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

        # --- 2. 루트 경로 임시 확인 및 .gitignore 파싱 (validate_paths 전에 필요) ---
        # validate_paths 내부에서 root 경로의 존재 유무는 다시 체크하지만, gitignore 파싱을 위해 먼저 필요
        temp_root_str = raw_config.get('root')
        if not temp_root_str or not isinstance(temp_root_str, str):
             raise typer.BadParameter("YAML 'root' key is missing or not a string.")
        # YAML 파일 위치 기준 상대 경로 해석 후 절대 경로화
        prospective_root_for_gitignore = (config_path.parent / Path(temp_root_str)).resolve()
        if not prospective_root_for_gitignore.is_dir():
             # validate_paths에서 더 자세한 오류 메시지 제공하므로 여기선 간단히 넘어감
              pass # Or raise a preliminary error if preferred

        gitignore_spec = parse_gitignore(prospective_root_for_gitignore)
        if gitignore_spec:
            typer.echo(f"Parsed .gitignore (and ignoring .git/) from '{prospective_root_for_gitignore}'.")
        else:
            typer.echo(f"No .gitignore found in '{prospective_root_for_gitignore}'. Only ignoring .git/.")


        # --- 3. 경로 상세 검증, Glob 확장 및 PathsConfig 생성 ---
        typer.echo("Validating root path and processing 'codes' patterns...")
        # raw_config['codes'] (패턴 리스트)와 gitignore_spec 전달
        config = validate_paths(config_path, raw_config['root'], raw_config['codes'], gitignore_spec)
        root_dir = config.root # 검증된 절대 경로
        relative_code_paths = config.codes # Glob 확장 및 .gitignore 필터링 후 실제 존재하는 파일 목록 (상대 경로)

        typer.echo(f"Processing project root: {root_dir}")
        if not relative_code_paths:
             # validate_paths에서 이미 경고했을 수 있지만, 최종 확인
             typer.secho("Warning: No code files were found to aggregate based on the config patterns and .gitignore rules.", fg=typer.colors.YELLOW, err=True)


        # --- 4. 디렉토리 트리 생성 ---
        # generate_tree는 이미 gitignore_spec을 사용하므로 변경 없음
        typer.echo("Generating directory tree...")
        tree_output = generate_tree(root_dir, gitignore_spec)

        # --- 5. 코드 취합 ---
        # aggregate_codes는 파일 경로 리스트를 받으므로 변경 없음
        if relative_code_paths:
             typer.echo(f"Aggregating {len(relative_code_paths)} code file(s)...")
             code_output = aggregate_codes(root_dir, relative_code_paths)
        else:
             code_output = "[No code files to aggregate]" # 메시지 유지

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
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(final_output, encoding='utf-8')
            typer.secho(f"Successfully generated output to {output_path}", fg=typer.colors.GREEN)
        except Exception as e:
             typer.secho(f"Error writing output file {output_path}: {e}", fg=typer.colors.RED, err=True)
             raise typer.Exit(code=2)

    except typer.BadParameter as e:
        typer.secho(f"Configuration Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED, err=True)
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=3)

if __name__ == "__main__":
    app()