# src/project_aggregator/models.py
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List

class PathsConfig(BaseModel):
    """YAML 설정 파일의 구조를 정의하고 유효성을 검사하는 모델"""
    root: Path              # 프로젝트 루트 경로 (절대 경로로 변환됨)
    codes: List[Path]       # 취합할 코드 파일 목록 (root 기준 상대 경로)

    # Pydantic 모델 설정 (예: 임의의 추가 필드 허용 안 함)
    class Config:
        extra = 'forbid'