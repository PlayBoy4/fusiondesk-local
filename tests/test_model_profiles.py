from fusiondesk.core import ModelCatalog


def test_godmode_local_profile_is_registered():
    profile = ModelCatalog.load().get("godmode-local")

    assert profile["display_name"] == "Godmode Local Clone"
    assert profile["source_reference"] == "G0DM0D3"
    assert profile["integration_status"] == "profile_only"

