import json
import os

from comfywrap.core.output import collect_and_write, unique_path


def test_unique_path_avoids_collision(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    assert unique_path(str(tmp_path), "a.mp4").endswith("a_1.mp4")


def test_collect_copies_and_writes_sidecar(tmp_path):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"vid")
    final, sidecar = collect_and_write(str(src), str(tmp_path / "out"), {"k": "v"})
    assert os.path.exists(final)
    assert os.path.exists(sidecar)
    assert json.load(open(sidecar, encoding="utf-8"))["k"] == "v"


def test_collect_without_output_dir_leaves_in_place(tmp_path):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"vid")
    final, sidecar = collect_and_write(str(src), None, {"k": 1})
    assert final == str(src)
    assert sidecar == str(src) + ".json"
    assert os.path.exists(sidecar)
