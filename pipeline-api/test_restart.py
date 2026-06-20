"""Tests for service restart endpoints."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import docker

# Import the FastAPI app
from main import app, _RESTARTABLE_SERVICES
from fastapi.testclient import TestClient


client = TestClient(app)


class TestRestartService:
    """Tests for POST /dash/restart/{service}"""

    def test_restart_allowed_service_success(self):
        """Restart an allowed service that is running."""
        with patch("docker.from_env") as mock_docker:
            mock_client = Mock()
            mock_container = Mock()
            mock_docker.return_value = mock_client
            mock_client.containers.get.return_value = mock_container

            response = client.post("/dash/restart/postgres")

            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "postgres"
            assert data["status"] == "restarted"
            mock_client.containers.get.assert_called_once_with("postgres")
            mock_container.restart.assert_called_once_with(timeout=10)

    def test_restart_all_allowed_services(self):
        """Verify allowlist includes expected services."""
        expected = {"postgres", "openclaw", "cliproxy", "n8n", "arcreel"}
        assert _RESTARTABLE_SERVICES == expected

    def test_restart_pipeline_api_rejected(self):
        """Cannot restart pipeline-api to avoid killing the request."""
        response = client.post("/dash/restart/pipeline-api")
        assert response.status_code == 400
        data = response.json()
        assert "cannot restart pipeline-api" in data["detail"]

    def test_restart_unknown_service_rejected(self):
        """Reject unknown service names."""
        response = client.post("/dash/restart/unknown-service")
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "unknown service"

    def test_restart_container_not_running(self):
        """Container not found returns not_running status (200, not error)."""
        with patch("docker.from_env") as mock_docker:
            mock_client = Mock()
            mock_docker.return_value = mock_client
            mock_client.containers.get.side_effect = docker.errors.NotFound("container not found")

            response = client.post("/dash/restart/arcreel")

            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "arcreel"
            assert data["status"] == "not_running"

    def test_restart_docker_error_generic(self):
        """Generic docker errors redact internals."""
        with patch("docker.from_env") as mock_docker:
            mock_client = Mock()
            mock_docker.return_value = mock_client
            mock_client.containers.get.side_effect = Exception("Permission denied")

            with patch("builtins.print") as mock_print:
                response = client.post("/dash/restart/openclaw")

                assert response.status_code == 200
                data = response.json()
                assert data["service"] == "openclaw"
                assert data["status"] == "error"
                # Verify error was logged server-side (not exposed to client)
                mock_print.assert_called_once()
                call_args = mock_print.call_args[0][0]
                assert "[restart/openclaw]" in call_args
                assert "error" in call_args

    def test_restart_docker_socket_unavailable(self):
        """Docker socket unavailable raises at import time."""
        with patch("docker.from_env") as mock_docker:
            mock_docker.side_effect = Exception("Cannot connect to Docker daemon")

            response = client.post("/dash/restart/postgres")

            # Since the error is not a NotFound, it's caught as generic Exception
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"


class TestRestartAll:
    """Tests for POST /dash/restart-all"""

    def test_restart_all_success(self):
        """Restart all services successfully."""
        with patch("docker.from_env") as mock_docker:
            mock_client = Mock()
            mock_containers = {
                "postgres": Mock(),
                "openclaw": Mock(),
                "cliproxy": Mock(),
                "n8n": Mock(),
                "arcreel": Mock(),
            }

            def get_container(name):
                if name in mock_containers:
                    return mock_containers[name]
                raise docker.errors.NotFound(f"No such container: {name}")

            mock_client.containers.get.side_effect = get_container
            mock_docker.return_value = mock_client

            response = client.post("/dash/restart-all")

            assert response.status_code == 200
            data = response.json()
            assert data["restarted"] == 5
            assert len(data["results"]) == 5
            # Verify all containers were restarted
            for service_name in _RESTARTABLE_SERVICES:
                result = next((r for r in data["results"] if r["service"] == service_name), None)
                assert result is not None
                assert result["status"] == "restarted"
                mock_containers[service_name].restart.assert_called_once_with(timeout=10)

    def test_restart_all_partial_success(self):
        """Some containers running, some not, no complete failure."""
        with patch("docker.from_env") as mock_docker:
            mock_client = Mock()
            mock_postgres = Mock()
            mock_docker.return_value = mock_client

            def get_container(name):
                if name == "postgres":
                    return mock_postgres
                elif name in ["openclaw", "n8n"]:
                    raise docker.errors.NotFound(f"No such container: {name}")
                else:
                    return Mock()

            mock_client.containers.get.side_effect = get_container

            response = client.post("/dash/restart-all")

            assert response.status_code == 200
            data = response.json()
            # postgres, cliproxy, arcreel restarted (3)
            assert data["restarted"] == 3
            assert len(data["results"]) == 5

            # Verify mix of statuses
            statuses = {r["service"]: r["status"] for r in data["results"]}
            assert statuses["postgres"] == "restarted"
            assert statuses["openclaw"] == "not_running"
            assert statuses["n8n"] == "not_running"
            assert statuses["cliproxy"] == "restarted"
            assert statuses["arcreel"] == "restarted"

    def test_restart_all_with_errors(self):
        """Some services fail, but restart-all continues."""
        with patch("docker.from_env") as mock_docker:
            mock_client = Mock()
            mock_openclaw = Mock()
            mock_cliproxy = Mock()

            def get_container(name):
                if name == "postgres":
                    return Mock()
                elif name == "openclaw":
                    return mock_openclaw
                elif name == "cliproxy":
                    return mock_cliproxy
                else:
                    return Mock()

            mock_client.containers.get.side_effect = get_container
            # openclaw restart raises a generic error
            mock_openclaw.restart.side_effect = Exception("Runtime error")
            mock_docker.return_value = mock_client

            with patch("builtins.print") as mock_print:
                response = client.post("/dash/restart-all")

                assert response.status_code == 200
                data = response.json()
                # postgres, cliproxy, n8n?, arcreel? (some succeed despite openclaw error)
                assert data["restarted"] >= 3  # At least 3 should succeed
                assert len(data["results"]) == 5

                # Verify openclaw shows error status
                openclaw_result = next((r for r in data["results"] if r["service"] == "openclaw"), None)
                assert openclaw_result is not None
                assert openclaw_result["status"] == "error"

                # Verify error was logged
                assert mock_print.called

    def test_restart_all_docker_unavailable(self):
        """Docker socket unavailable (error at client creation)."""
        with patch("docker.from_env") as mock_docker:
            mock_docker.side_effect = Exception("Cannot connect to Docker daemon")

            with patch("builtins.print") as mock_print:
                response = client.post("/dash/restart-all")

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "error"
                assert data["detail"] == "docker unavailable"
                mock_print.assert_called_once()


class TestRestartIntegration:
    """Integration-style tests combining multiple endpoints."""

    def test_services_endpoint_includes_restartable(self):
        """Verify /dash/services lists services that can be restarted."""
        with patch("docker.from_env"):
            with patch("httpx.get"):
                response = client.get("/dash/services")
                assert response.status_code == 200
                data = response.json()
                service_names = {s["name"] for s in data["services"]}
                # All restartable services should be in the services list
                assert _RESTARTABLE_SERVICES.issubset(service_names)
