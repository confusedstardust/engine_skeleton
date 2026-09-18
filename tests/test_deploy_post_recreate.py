from pathlib import Path


def test_post_deployment_recreates_backend_with_running_images():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/docker-publish-deploy.yml").read_text(encoding="utf-8")
    deployed = workflow.index('Finished docker compose up')
    post = workflow.index('cd /var/www/myproject', deployed)
    backend = workflow.index('export BACKEND_IMAGE="$(docker inspect --format', post)
    frontend = workflow.index('export FRONTEND_IMAGE="$(docker inspect --format', backend)
    recreate = workflow.index('docker-compose -f docker-compose.prod.yml up -d --force-recreate backend', frontend)
    assert deployed < post < backend < frontend < recreate
