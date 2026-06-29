"""Gitea client PR tests (Slice 6D)."""

from unittest.mock import MagicMock, patch

from agent_control.gitea_client import GiteaClient


def test_create_pull_request() -> None:
    client = GiteaClient()
    client.token = "tok"
    client.base_url = "http://gitea.local"
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"number": 7, "html_url": "http://gitea.local/pr/7"}
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.Client") as mock_client:
        instance = mock_client.return_value.__enter__.return_value
        instance.post.return_value = mock_resp
        result = client.create_pull_request(
            "owner",
            "repo",
            head="agent/run-1",
            base="main",
            title="agent(fix): WI-1",
            body="test body",
            run_id="run-1",
        )
    assert result["number"] == 7
    instance.post.assert_called_once()
    call_kwargs = instance.post.call_args
    assert call_kwargs[1]["json"]["head"] == "agent/run-1"
    assert call_kwargs[1]["json"]["base"] == "main"


def test_get_branch_sha() -> None:
    client = GiteaClient()
    client.token = "tok"
    client.base_url = "http://gitea.local"
    with patch.object(client, "get_branch", return_value={"commit": {"id": "sha123"}}):
        assert client.get_branch_sha("o", "r", "main") == "sha123"
