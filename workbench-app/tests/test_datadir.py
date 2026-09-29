"""Data-folder separation: live programs live outside the repo."""
import json

from workbench import datadir
from workbench.server import create_app

from test_server import approot  # noqa: F401  (fixture)


def _repo(tmp_path):
    app = tmp_path / "repo" / "workbench-app"
    app.mkdir(parents=True)
    ex = tmp_path / "repo" / "examples" / "demo-a" / "governed"
    ex.mkdir(parents=True)
    (ex / "purpose_statement.json").write_text("{}")
    return app


def test_default_is_sibling_of_repo(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKBENCH_DATA", raising=False)
    app = _repo(tmp_path)
    assert datadir.resolve(app) == (tmp_path / "workbench-data").resolve()


def test_env_and_explicit_precedence(tmp_path, monkeypatch):
    app = _repo(tmp_path)
    monkeypatch.setenv("WORKBENCH_DATA", str(tmp_path / "envdata"))
    assert datadir.resolve(app) == (tmp_path / "envdata").resolve()
    assert datadir.resolve(app, tmp_path / "x") == (tmp_path / "x").resolve()
    assert datadir.resolve(app, legacy_root=True) == app


def test_seed_only_on_first_run(tmp_path):
    app = _repo(tmp_path)
    data = tmp_path / "workbench-data"
    assert datadir.seed_examples(app, data) == ["demo-a"]
    assert (data / "programs/demo-a/governed/purpose_statement.json").exists()
    (data / "programs/demo-a/governed/purpose_statement.json").write_text('{"mine": 1}')
    assert datadir.seed_examples(app, data) == []          # never re-seeds / overwrites
    assert json.loads((data / "programs/demo-a/governed/purpose_statement.json").read_text()) == {"mine": 1}


def test_publish_copies_only_existing_examples_and_skips_restricted(tmp_path):
    app = _repo(tmp_path)
    data = tmp_path / "workbench-data"
    datadir.seed_examples(app, data)
    g = data / "programs/demo-a"
    (g / "governed/purpose_statement.json").write_text('{"v": 2}')
    (g / "restricted").mkdir()
    (g / "restricted/interview.json").write_text("secret")
    (data / "programs/live-bank").mkdir()
    (data / "programs/live-bank/x.json").write_text("private")
    report = datadir.publish_examples(app, data)
    ex = tmp_path / "repo/examples"
    assert json.loads((ex / "demo-a/governed/purpose_statement.json").read_text()) == {"v": 2}
    assert not (ex / "demo-a/restricted").exists()
    assert not (ex / "live-bank").exists()
    assert list(report) == ["demo-a"]


def test_app_uses_data_folder(tmp_path, approot):  # noqa: F811
    data = tmp_path / "separate-data"
    app = create_app(root=approot, api_key="k", data=data)
    st = app.state.wb
    assert st.data == data.resolve() and st.root == approot
    st_programs = st.data / "programs"
    (st_programs / "p1").mkdir(parents=True)
    assert st.pdir("p1") == st_programs / "p1"
