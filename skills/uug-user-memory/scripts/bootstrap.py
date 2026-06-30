#!/usr/bin/env python3
"""bootstrap.py — user-memory 데이터레이어 인스턴스 초기화.

사용: python3 bootstrap.py <target-dir>
  <target-dir> 에 user-memory 인스턴스를 만든다(스킬=엔진, 데이터=별도 레이어, MSM 패턴).
  - schema.yaml 복사 (types: UC/UP/UF — wm_node 가 이걸 읽음)
  - 티어 디렉토리(context/pattern/preference) + graph conventions 생성
  - .gitignore 시드(.zvec 인덱스 제외)
이후: WORKMEM_DIR=<target-dir> python3 wm_node.py new user-context --title ...
데이터레이어 위치는 사용자 선택(예: vault 루트 별도 계층). 절대경로 하드코딩 없음.
"""
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_SRC = SKILL_DIR / "schema.yaml"
REFERENCES_SRC = SKILL_DIR / "references"


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    target = Path(sys.argv[1]).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    for tier in ("context", "pattern", "preference"):
        (target / tier).mkdir(exist_ok=True)
    for subdir in ("context/repositories", "pattern/episodic", "graph", "references/json-schema", "references/jsonl-queries"):
        (target / subdir).mkdir(parents=True, exist_ok=True)
    shutil.copy(SCHEMA_SRC, target / "schema.yaml")
    if REFERENCES_SRC.exists():
        for source in REFERENCES_SRC.rglob("*"):
            if source.is_file():
                dest = target / "references" / source.relative_to(REFERENCES_SRC)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(source, dest)
    gi = target / ".gitignore"
    if not gi.exists():
        gi.write_text(".zvec/\n", encoding="utf-8")
    print(f"[bootstrap] user-memory 인스턴스 생성: {target}")
    print(f"  티어: context/ pattern/ preference/ graph/ + schema.yaml(UC/UP/UF)")
    print(f"  사용: WORKMEM_DIR=\"{target}\" python3 {SKILL_DIR}/scripts/wm_node.py new user-context --title \"...\" --tags a,b")
    return 0


if __name__ == "__main__":
    sys.exit(main())
