"""백엔드 영상 엔드포인트 엔드투엔드 스모크 — 실영상 1편을 API로 흘려본다.

검증 범위(모킹 없음, 실제 제품 경로 그대로):
  가입/로그인 → POST /inference/video (multipart 업로드) → AI 엔진(YOLO)
  → 리포트 JSON → 세트 변환(to_set) → /sessions 저장까지.

M0 체크리스트 "실제 영상으로 엔드투엔드 1회"의 재실행 가능한 형태다.
pytest 스위트에 넣지 않은 이유: ML 런타임 + 수십 초의 추론이 필요해서
단위 테스트와 성격이 다르다(스위트는 접합부만 검증한다).

사용: py -3 tools/smoke_video_endpoint.py [영상경로] [exercise_id]
      (기본: data/videos/squat_001.mp4, squat)
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault(
    "HOHOWATT_DB", os.path.join(tempfile.gettempdir(), "hohowatt_smoke.db"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

import db  # noqa: E402
import main  # noqa: E402


def run(video: Path, exercise_id: str) -> int:
    db.reset()
    client = TestClient(main.app)

    r = client.post("/auth/register",
                    json={"email": "smoke@test.com", "password": "pw123"})
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    print(f"[1/4] 가입·로그인 OK")

    t0 = time.monotonic()
    with video.open("rb") as fh:
        r = client.post(
            "/inference/video", headers=headers,
            data={"exercise_id": exercise_id},
            files={"video": (video.name, fh, "video/mp4")},
        )
    elapsed = time.monotonic() - t0
    if r.status_code != 200:
        print(f"[2/4] 업로드·분석 실패: {r.status_code} {r.text}")
        return 1
    body = r.json()
    report, set_data = body["report"], body["set"]
    print(f"[2/4] 업로드·분석 OK ({elapsed:.1f}s) — rep {report['rep_count']}, "
          f"판정 {[v['verdict'] for v in report.get('rep_verdicts', [])]}")
    assert "annotated_video_path" not in report, "서버 로컬 경로가 응답에 새어 나감"

    r = client.post("/sessions", headers=headers, json={
        "exercise_id": exercise_id,
        "started_at": "2026-08-10T12:00:00",
        "sets": [set_data],
    })
    assert r.status_code == 201, r.text
    session = r.json()
    print(f"[3/4] 세션 저장 OK — sets[0].reps={session['sets'][0]['reps']}, "
          f"avg_form_score={session['avg_form_score']}")

    r = client.get(f"/sessions/{session['id']}/analysis", headers=headers)
    assert r.status_code == 200, r.text
    print(f"[4/4] 분석 조회 OK — has_score={r.json().get('has_score')}")
    print("\n엔드투엔드 스모크 통과 ✅")
    return 0


if __name__ == "__main__":
    video = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/videos/squat_001.mp4")
    exercise = sys.argv[2] if len(sys.argv) > 2 else "squat"
    raise SystemExit(run(video, exercise))
