from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_required_repo_tree_exists():
    for rel in [
        "Dockerfile",
        "render.yaml",
        "requirements.txt",
        "src/titanbox/main.py",
        "src/titanbox/telegram.py",
        "src/titanbox/plugins/deploy_admin.py",
        "scripts/entrypoint.sh",
        "scripts/preflight_repo.py",
        "config/apps.toml",
        "nginx/nginx.conf.template",
    ]:
        assert ROOT.joinpath(rel).exists(), rel


def test_render_blueprint_is_free_tier_safe_and_bootstrapped():
    text = ROOT.joinpath("render.yaml").read_text()
    assert "plan: free" in text
    assert "maxShutdownDelaySeconds" not in text
    assert "autoDeployTrigger: commit" in text
    assert 'key: AUTO_REGISTER_WEBHOOKS' in text
    assert 'value: "true"' in text
    assert "deploy-admin" in text
    assert "DEPLOY_BOT_TOKEN" in text
    assert "sync: false" in text
    assert "PUBLIC_BASE_URL" not in text
    assert "placeholder.invalid" not in text


def test_dockerfile_uses_single_context_copy_with_clear_preflight():
    text = ROOT.joinpath("Dockerfile").read_text()
    assert "COPY --chown=app:app . /app" in text
    assert "repository is incomplete" in text
    assert "COPY src /app/src" not in text
