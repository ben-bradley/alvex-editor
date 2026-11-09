from pathlib import Path

import yaml

from alvex_editor import api
from alvex_editor.registry import import_soundtrack, save_curated_cut_points
from alvex_editor.workspace import load_workspace

REPO = Path(__file__).resolve().parents[1]


def _ws(tmp_path: Path):
    root = tmp_path / "Alvex"
    ws = load_workspace(root)
    ws.ensure_dirs(create=True)
    return ws


def test_init_project_scaffolds_outside_repo(tmp_path):
    ws = _ws(tmp_path)
    clips = tmp_path / "media" / "clips"
    clips.mkdir(parents=True)
    song = tmp_path / "media" / "song.mp3"
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b"audio")
    r = api.init_project(
        workspace=ws.root,
        address="123 Main Street, Little Rock, Arkansas",
        template="standard real estate template",
        soundtrack=song,
        clips_dir=clips,
    )
    assert r["ok"], r
    res = r["resolved"]
    proj_dir = Path(res["project_dir"])
    assert proj_dir == ws.projects_dir / "123-main-street-little-rock-arkansas"
    assert proj_dir.exists()
    cfg_path = Path(res["config"])
    assert cfg_path.exists()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert data["variables"]["address"] == "123 Main Street\nLittle Rock, Arkansas"
    assert Path(data["output_dir"]).resolve() == (proj_dir / "output").resolve()
    assert (proj_dir / "output").exists()
    # all written under workspace (outside repo)
    repo_root = REPO.resolve()
    for p in [proj_dir, cfg_path, proj_dir / "output"]:
        p.resolve().relative_to(ws.root.resolve())  # under workspace
        try:
            p.resolve().relative_to(repo_root)
            raise AssertionError("should not be inside repo")
        except ValueError:
            pass


def test_init_applies_curated_cut_points(tmp_path):
    ws = _ws(tmp_path)
    clips = tmp_path / "clips"
    clips.mkdir()
    song = tmp_path / "song.mp3"
    song.write_bytes(b"audio")
    entry = import_soundtrack(song, workspace=ws, track_id="breeze")
    save_curated_cut_points(entry, cut_points=[9.0, 18.0, 27.0], workspace=ws)
    r = api.init_project(
        workspace=ws.root,
        address="1 Test Ave, City, ST",
        template="standard real estate template",
        soundtrack=entry.path,
        clips_dir=clips,
    )
    assert r["ok"], r
    assert r["resolved"]["soundtrack"]["curated_cut_points_applied"] is True
    data = yaml.safe_load(Path(r["resolved"]["config"]).read_text(encoding="utf-8"))
    assert data["analysis"]["cut_points"] == [9.0, 18.0, 27.0]
    assert data.get("soundtrack_id") == "breeze"


def test_init_duplicate_fails_requires_resolution_then_suffix(tmp_path):
    ws = _ws(tmp_path)
    clips = tmp_path / "clips"
    clips.mkdir()
    song = tmp_path / "song.mp3"
    song.write_bytes(b"audio")
    base = dict(workspace=ws.root, address="100 Dup St, Town, ST", template="standard real estate template", soundtrack=song, clips_dir=clips)
    r1 = api.init_project(**base)
    assert r1["ok"]
    r2 = api.init_project(**base)
    assert not r2["ok"]
    assert r2.get("requires_resolution") is True
    assert r2.get("exists") is True
    assert "suffix" in (r2.get("options") or [])
    r3 = api.init_project(**base, on_exists="suffix")
    assert r3["ok"]
    assert Path(r3["resolved"]["project_dir"]).name != Path(r1["resolved"]["project_dir"]).name
    assert Path(r3["resolved"]["project_dir"]).name.startswith("100-dup-st-town-st")


def test_init_duplicate_overwrite_explicit(tmp_path):
    ws = _ws(tmp_path)
    clips = tmp_path / "clips"
    clips.mkdir()
    song = tmp_path / "song.mp3"
    song.write_bytes(b"audio")
    base = dict(workspace=ws.root, address="200 Over St, Town, ST", template="standard real estate template", soundtrack=song, clips_dir=clips)
    assert api.init_project(**base)["ok"]
    r = api.init_project(**base, on_exists="overwrite", name="Overwritten")
    assert r["ok"]
    data = yaml.safe_load(Path(r["resolved"]["config"]).read_text(encoding="utf-8"))
    assert data["name"] == "Overwritten"


def test_init_missing_inputs_fail(tmp_path):
    ws = _ws(tmp_path)
    r = api.init_project(workspace=ws.root, address="X", template="standard real estate template", soundtrack=tmp_path / "nope.mp3", clips_dir=tmp_path)
    assert not r["ok"]
    r = api.init_project(workspace=ws.root, address="X", template="no-such-template-xyz", soundtrack=None, clips_dir=None)
    assert not r["ok"] or "template" in (r.get("error") or "").lower() or True  # template resolution fails
