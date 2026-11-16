import importlib.util
from pathlib import Path
import tarfile

SPEC = importlib.util.spec_from_file_location("deploy_bundle", Path(__file__).parents[1]/"deploy/deploy_system.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_release_excludes_credentials_cache_and_training_data(tmp_path):
    for name in ["backend/app.py", "backend/.env", "backend/__pycache__/app.pyc", "deploy/bootstrap_edge.py",
                 "integrations/gui/project/dist/index.html", "integrations/face_recognition/photos/me.jpg",
                 "data/training.jpg", "backend/private.key", "deploy/local/password.json", "backend/credentials.json"]:
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test")
    output = tmp_path/"release.tar.gz"
    names = module.build_archive(tmp_path, output)
    assert "backend/app.py" in names
    assert "integrations/face_recognition/photos/me.jpg" in names
    assert not any(".env" in n or "__pycache__" in n or "private.key" in n or n.startswith("data/") for n in names)
    assert "deploy/local/password.json" not in names
    assert "backend/credentials.json" not in names
    with tarfile.open(output) as archive:
        assert set(archive.getnames()) == set(names)
