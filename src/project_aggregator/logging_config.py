# src/project_aggregator/logging_config.py
import logging
import logging.config
import yaml
from pathlib import Path
import coloredlogs # coloredlogs 포매터 인식 및 install 호출 위해 임포트 필요
import sys

# 로거 인스턴스 가져오기 (설정 과정 자체 로깅용)
# 이 로거는 설정이 완료되기 전에 사용될 수 있으므로 기본 설정이 적용될 수 있음
config_logger = logging.getLogger(__name__)

def setup_logging():
    """YAML 설정 파일을 로드하여 로깅 시스템을 설정합니다."""

    # --- 수정된 부분 시작 ---
    # dictConfig를 호출하기 전에 coloredlogs.install()을 먼저 호출하여
    # 컬러 로깅에 필요한 전역 설정을 초기화합니다.
    # 이렇게 하면 dictConfig가 ColoredFormatter를 로드할 때
    # 필요한 환경이 준비되어 있을 가능성이 높아집니다.
    # 인자 없이 호출하면 기본적인 설정을 시도합니다.
    try:
        coloredlogs.install()
        # 초기 install 성공 로그 (아직 포맷 지정 전일 수 있음)
        config_logger.debug("Called coloredlogs.install() for initial setup.")
    except Exception as install_e:
        # coloredlogs 설치 실패 시 경고 출력 (기본 로깅 사용)
        print(f"Warning: coloredlogs.install() failed during initial setup: {install_e}", file=sys.stderr)
    # --- 수정된 부분 끝 ---

    config_path = Path(__file__).parent.parent / 'logging_config.yaml' # 경로 수정: project_aggregator 폴더 밖에 있음
    config = None # config 변수 초기화

    try:
        if config_path.is_file(): # is_file()로 변경 (더 명확함)
            config_logger.debug(f"Found logging configuration file: {config_path}")
            with open(config_path, 'rt', encoding='utf-8') as f:
                config = yaml.safe_load(f.read())

            if config:
                logging.config.dictConfig(config)
                # dictConfig 적용 후 로깅 (이제 YAML에 정의된 포맷/레벨 적용됨)
                logging.getLogger("project_aggregator").debug("Logging setup complete from YAML using dictConfig.")
            else:
                # YAML 파일은 있지만 내용이 비어있는 경우
                print(f"Warning: Logging configuration file {config_path} is empty. Using basicConfig.", file=sys.stderr)
                logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
                logging.getLogger("project_aggregator").warning("YAML config file was empty. Fell back to basic logging configuration.")

        else:
            # 설정 파일이 아예 없는 경우
            print(f"Warning: Logging configuration file not found at {config_path}. Using basicConfig.", file=sys.stderr)
            # 기본 로깅 설정: 컬러 없이 INFO 레벨 이상 출력
            logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
            # coloredlogs 기본 설정을 다시 시도해볼 수 있음 (선택적)
            # coloredlogs.install(level='INFO')
            logging.getLogger("project_aggregator").warning(f"Logging config file not found ({config_path}). Fell back to basic logging configuration.")

    except yaml.YAMLError as yaml_e:
        # YAML 파싱 오류 처리
        print(f"Error parsing logging configuration file {config_path}: {yaml_e}", file=sys.stderr)
        print("Using basicConfig as fallback.", file=sys.stderr)
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("project_aggregator").error(f"Failed to parse logging config YAML: {yaml_e}")
    except Exception as e:
        # 기타 설정 로드 오류 처리
        print(f"Error loading logging configuration from {config_path}: {e}", file=sys.stderr)
        print("Using basicConfig as fallback.", file=sys.stderr)
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("project_aggregator").error(f"Failed to load logging config: {e}", exc_info=True) # 상세 오류 로깅

# --- 주석 처리된 부분 ---
# 모듈 로드 시 자동 적용 대신 main.py에서 명시적으로 호출하는 것이 좋습니다.
# setup_logging()
# --- 주석 처리 끝 ---

# --- 추가된 부분 (경로 수정 확인용) ---
# logging_config.yaml 파일의 실제 위치 확인 (루트 디렉토리)
ACTUAL_YAML_PATH = Path(__file__).parent.parent.parent / 'logging_config.yaml'
if not ACTUAL_YAML_PATH.exists():
    print(f"Note: The YAML configuration file expected at project root ({ACTUAL_YAML_PATH}) was not found. "
          f"The path used in setup_logging assumes it's in the 'project_aggregator' parent directory (src/). "
          f"Make sure `logging_config.yaml` is in the correct location (project root).", file=sys.stderr)
# --- 추가된 부분 끝 ---