import logging
import coloredlogs

def setup_logging():
    # 사용자 정의 설정으로 coloredlogs 설치
    coloredlogs.install(
        level='INFO',  # INFO 레벨 이상만 출력
        fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        level_styles={
            'debug': {'color': 'magenta'},
            'info': {'color': 'green', 'bold': True},
            'warning': {'color': 'yellow'},
            'error': {'color': 'red'},
            'critical': {'color': 'red', 'bold': True, 'background': 'white'}
        },
        field_styles={
            'asctime': {'color': 'cyan'},
            'levelname': {'color': 'black', 'bold': True},
            'name': {'color': 'blue'}
        }
    )