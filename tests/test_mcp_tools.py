import datetime as dt

from app.mcp_tools import _serialize_tool_result


def test_mcp_results_use_the_same_utc_timestamp_encoding_as_the_api() -> None:
    timestamp = dt.datetime(2026, 10, 9, 10, 20, 30, 456789, tzinfo=dt.UTC)

    result = _serialize_tool_result({"capturedAt": timestamp})

    assert result == {"capturedAt": "2026-10-09T10:20:30.456Z"}


async def test_mcp_entry_registers_the_documented_tool_set() -> None:
    from app.mcp import server

    tools = await server.list_tools()

    assert {tool.name for tool in tools} == {
        "list_spaces",
        "list_notes",
        "search_notes",
        "get_note",
        "update_space_description",
        "disconnect_trove",
    }
