from __future__ import annotations

import time

from broodmind.cli.main import _is_webapp_build_stale


def test_webapp_build_is_stale_when_dist_missing(tmp_path) -> None:
    webapp_dir = tmp_path / "webapp"
    webapp_dir.mkdir()
    (webapp_dir / "src").mkdir()
    (webapp_dir / "src" / "main.tsx").write_text("export {};\n", encoding="utf-8")
    dist_dir = webapp_dir / "dist"

    assert _is_webapp_build_stale(webapp_dir, dist_dir) is True


def test_webapp_build_not_stale_when_dist_newer(tmp_path) -> None:
    webapp_dir = tmp_path / "webapp"
    src_dir = webapp_dir / "src"
    dist_dir = webapp_dir / "dist"
    src_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True)

    source_file = src_dir / "main.tsx"
    source_file.write_text("console.log('a');\n", encoding="utf-8")
    time.sleep(0.01)
    (dist_dir / "index.html").write_text("<html></html>\n", encoding="utf-8")

    assert _is_webapp_build_stale(webapp_dir, dist_dir) is False


def test_webapp_build_stale_when_source_newer_than_dist(tmp_path) -> None:
    webapp_dir = tmp_path / "webapp"
    src_dir = webapp_dir / "src"
    dist_dir = webapp_dir / "dist"
    src_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True)

    source_file = src_dir / "main.tsx"
    source_file.write_text("console.log('a');\n", encoding="utf-8")
    (dist_dir / "index.html").write_text("<html></html>\n", encoding="utf-8")
    time.sleep(0.01)
    source_file.write_text("console.log('b');\n", encoding="utf-8")

    assert _is_webapp_build_stale(webapp_dir, dist_dir) is True
