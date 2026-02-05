# mcp-server-dexcom-health

MCP server for Dexcom CGM glucose data. Enables AI agents to access and analyze continuous glucose monitor data for health intelligence applications.

## Features

- **Real-time glucose monitoring** - Current readings with trend analysis
- **Historical data access** - Up to 24 hours of glucose history
- **Clinical analytics** - Time-in-range, GMI, CV%, AGP reports
- **Episode detection** - Automatic hypo/hyper event identification with detailed context
- **Time-block analysis** - Identify patterns by time of day
- **Persistence layer support** - Pass external data for long-term analysis

## Tools

| Tool | Description |
|------|-------------|
| `get_current_glucose` | Current glucose reading with trend |
| `get_glucose_readings` | Historical readings (up to 24h) |
| `get_statistics` | TIR, CV%, GMI, and other metrics |
| `get_status_summary` | Complete "how am I doing?" summary |
| `detect_episodes` | Find hypo/hyper episodes |
| `get_episode_details` | Deep analysis of each episode |
| `analyze_time_blocks` | Patterns by time of day |
| `check_alerts` | Real-time threshold alerts |
| `export_data` | Export for external storage |
| `get_agp_report` | Clinical AGP report |

## Installation
```bash
# Using uvx (recommended)
uvx mcp-server-dexcom-health

# Using pip
pip install mcp-server-dexcom-health
```

## Configuration

Set environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DEXCOM_USERNAME` | Yes | Dexcom username, email, or phone (+1234567890) |
| `DEXCOM_PASSWORD` | Yes | Dexcom password |
| `DEXCOM_REGION` | No | `us` (default), `ous` (outside US), or `jp` (Japan) |

### Claude Desktop

Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "dexcom": {
      "command": "uvx",
      "args": ["mcp-server-dexcom-health"],
      "env": {
        "DEXCOM_USERNAME": "your_username",
        "DEXCOM_PASSWORD": "your_password",
        "DEXCOM_REGION": "us"
      }
    }
  }
}
```

## Usage Examples

### Basic usage with Claude

> "What's my current glucose?"

> "How was my overnight control?"

> "Did I have any lows today?"

> "Give me my statistics for the last 12 hours"

### Persistence Layer Integration

Tools that analyze data accept an optional `data` parameter for external data sources:
```python
# Pass your own historical data
result = get_statistics(
    data=[
        {"glucose_mg_dl": 120, "timestamp": "2024-01-15T08:00:00"},
        {"glucose_mg_dl": 135, "timestamp": "2024-01-15T08:05:00"},
        # ... more readings
    ]
)
```

This enables building long-term analytics by storing data externally and passing it back for analysis.

## Requirements

- Python 3.10+
- Active Dexcom Share session (requires Dexcom mobile app with Share enabled)
- At least one follower configured in Dexcom Share

## License

MIT