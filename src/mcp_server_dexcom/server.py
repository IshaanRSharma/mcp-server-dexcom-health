import os
from pydexcom import Dexcom
from mcp.server.fastmcp import FastMCP
from statistics import mean, stdev

mcp = FastMCP(
    "Dexcom Glucose",
    instructions="Access and analyze Dexcom CGM glucose data.",
)

def get_dexcom_client() -> Dexcom:
    """Create Dexcom client from environment variables."""
    username = os.getenv("DEXCOM_USERNAME")
    password = os.getenv("DEXCOM_PASSWORD")
    region = os.getenv("DEXCOM_REGION", "us")
    
    if not username or not password:
        raise ValueError(
            "DEXCOM_USERNAME and DEXCOM_PASSWORD environment variables required"
        )
    
    if region == "ous":
        return Dexcom(username=username, password=password, region="ous")
    elif region == "jp":
        return Dexcom(username=username, password=password, region="jp")
    else:
        return Dexcom(username=username, password=password)

def parse_external_data(data: list[dict]) -> list:
    """Convert external data format to internal reading objects."""
    from datetime import datetime
    
    class ExternalReading:
        def __init__(self, glucose: int, timestamp: str):
            self.value = glucose
            self.datetime = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    
    return [ExternalReading(d["glucose_mg_dl"], d["timestamp"]) for d in data]

@mcp.tool()
def get_current_glucose() -> dict:
    """
    Get the current glucose reading.
    
    Returns the most recent glucose value, trend direction, 
    and timestamp. Reading must be within the last 10 minutes.
    """
    client = get_dexcom_client()
    reading = client.get_current_glucose_reading()
    
    if reading is None:
        return {
            "status": "no_data",
            "message": "No current glucose reading available (must be within 10 minutes)"
        }
    
    return {
        "glucose_mg_dl": reading.value,
        "glucose_mmol_l": reading.mmol_l,
        "trend": reading.trend_direction,
        "trend_arrow": reading.trend_arrow,
        "trend_description": reading.trend_description,
        "timestamp": reading.datetime.isoformat(),
    }

@mcp.tool()
def get_glucose_readings(
    minutes: int = 60,
    max_count: int = 12,
    data: list[dict] | None = None
) -> dict:
    """
    Get historical glucose readings.
    
    Args:
        minutes: Number of minutes to look back (1-1440, default 60)
        max_count: Maximum readings to return (1-288, default 12)
        data: Optional external readings for persistence layer integration.
    """
    if data:
        readings = parse_external_data(data)
        # Apply max_count limit
        readings = sorted(readings, key=lambda r: r.datetime, reverse=True)[:max_count]
    else:
        minutes = max(1, min(1440, minutes))
        max_count = max(1, min(288, max_count))
        client = get_dexcom_client()
        readings = client.get_glucose_readings(minutes=minutes, max_count=max_count)
    
    if not readings:
        return {
            "status": "no_data",
            "message": f"No readings found",
            "readings": []
        }
    
    return {
        "count": len(readings),
        "readings": [
            {
                "glucose_mg_dl": r.value,
                "glucose_mmol_l": getattr(r, 'mmol_l', round(r.value / 18.0, 1)),
                "trend": getattr(r, 'trend_direction', None),
                "trend_arrow": getattr(r, 'trend_arrow', None),
                "timestamp": r.datetime.isoformat(),
            }
            for r in readings
        ]
    }

@mcp.tool()
def get_statistics(
    minutes: int = 1440,
    low: int = 70,
    high: int = 180,
    data: list[dict] | None = None
) -> dict:
    """
    Get glucose statistics for a time period.
    
    Args:
        minutes: Number of minutes to analyze (1-1440, default 1440 = 24h)
        low: Low threshold in mg/dL (default 70)
        high: High threshold in mg/dL (default 180)
        data: Optional external readings for persistence layer integration.
    """
    if data:
        readings = parse_external_data(data)
    else:
        minutes = max(1, min(1440, minutes))
        client = get_dexcom_client()
        readings = client.get_glucose_readings(minutes=minutes, max_count=288)
    
    if not readings:
        return {
            "status": "no_data",
            "message": "No readings found"
        }
    
    values = [r.value for r in readings]
    
    avg = mean(values)
    sd = stdev(values) if len(values) > 1 else 0.0
    cv = (sd / avg * 100) if avg > 0 else 0.0
    
    total = len(values)
    in_range = sum(1 for v in values if low <= v <= high)
    below = sum(1 for v in values if v < low)
    above = sum(1 for v in values if v > high)
    very_low = sum(1 for v in values if v < 54)
    very_high = sum(1 for v in values if v > 250)
    
    return {
        "reading_count": total,
        "mean_mg_dl": round(avg, 1),
        "mean_mmol_l": round(avg / 18.0, 1),
        "std_dev": round(sd, 1),
        "cv_percent": round(cv, 1),
        "min_mg_dl": min(values),
        "max_mg_dl": max(values),
        "time_in_range_percent": round(in_range / total * 100, 1),
        "time_below_percent": round(below / total * 100, 1),
        "time_above_percent": round(above / total * 100, 1),
        "time_very_low_percent": round(very_low / total * 100, 1),
        "time_very_high_percent": round(very_high / total * 100, 1),
        "thresholds": {"low": low, "high": high}
    }
       
@mcp.tool()
def get_status_summary(minutes: int = 180) -> dict:
    """
    Get a complete status summary - the "how am I doing?" tool.
    
    Returns current glucose, recent trend, stats for the specified period,
    any alerts, and a plain-English summary. Perfect for quick check-ins,
    clinical dashboards, or health intelligence apps.
    
    Args:
        minutes: Time period for context stats (1-1440, default 180 = 3 hours)
    
    Returns:
        - current: Real-time glucose, trend, arrow
        - period_stats: Average, min, max, time-in-range for the period
        - alerts: Any recent lows/highs detected
        - summary: Plain-English interpretation with urgency level
    """
    minutes = max(1, min(1440, minutes))
    
    client = get_dexcom_client()
    
    # Current reading
    current = client.get_current_glucose_reading()
    
    # Historical readings for context
    max_count = min(288, minutes // 5 + 1)
    readings = client.get_glucose_readings(minutes=minutes, max_count=max_count)
    
    if current is None and not readings:
        return {
            "status": "no_data",
            "message": "No glucose data available"
        }
    
    result = {"period_minutes": minutes}
    
    # Current state
    if current:
        result["current"] = {
            "glucose_mg_dl": current.value,
            "glucose_mmol_l": current.mmol_l,
            "trend": current.trend_direction,
            "trend_arrow": current.trend_arrow,
            "trend_description": current.trend_description,
            "timestamp": current.datetime.isoformat(),
        }
    
    # Period stats
    if readings:
        values = [r.value for r in readings]
        avg = sum(values) / len(values)
        
        in_range = sum(1 for v in values if 70 <= v <= 180)
        below = sum(1 for v in values if v < 70)
        above = sum(1 for v in values if v > 180)
        very_low = sum(1 for v in values if v < 54)
        very_high = sum(1 for v in values if v > 250)
        
        result["period_stats"] = {
            "average_mg_dl": round(avg, 1),
            "average_mmol_l": round(avg / 18.0, 1),
            "min_mg_dl": min(values),
            "max_mg_dl": max(values),
            "readings_count": len(values),
            "time_in_range_percent": round(in_range / len(values) * 100, 1),
            "time_below_percent": round(below / len(values) * 100, 1),
            "time_above_percent": round(above / len(values) * 100, 1),
        }
        
        # Alerts
        recent_lows = [r for r in readings if r.value < 70]
        recent_highs = [r for r in readings if r.value > 180]
        
        result["alerts"] = {
            "has_recent_lows": len(recent_lows) > 0,
            "has_recent_highs": len(recent_highs) > 0,
            "has_urgent_low": very_low > 0,
            "has_urgent_high": very_high > 0,
            "low_count": len(recent_lows),
            "high_count": len(recent_highs),
        }
    
    # Plain English summary
    if current:
        glucose = current.value
        
        if glucose < 54:
            level = "very low"
            urgency = "urgent"
        elif glucose < 70:
            level = "low"
            urgency = "attention"
        elif glucose <= 180:
            level = "in range"
            urgency = "normal"
        elif glucose <= 250:
            level = "high"
            urgency = "attention"
        else:
            level = "very high"
            urgency = "urgent"
        
        # Build summary text
        trend_text = current.trend_description or current.trend_direction
        summary_text = f"Currently {glucose} mg/dL ({level}), trending {trend_text}."
        
        if readings:
            tir = result["period_stats"]["time_in_range_percent"]
            hours = minutes / 60
            summary_text += f" Over the last {hours:.1f}h: {tir}% in range."
        
        result["summary"] = {
            "text": summary_text,
            "glucose_level": level,
            "urgency": urgency,
        }
    
    return result

@mcp.tool()
def detect_episodes(
    minutes: int = 1440,
    low: int = 70,
    high: int = 180,
    data: list[dict] | None = None
) -> dict:
    """
    Detect hypoglycemic and hyperglycemic episodes.
    
    Args:
        minutes: Time period if using Dexcom API (1-1440, default 1440 = 24h)
        low: Low threshold in mg/dL (default 70)
        high: High threshold in mg/dL (default 180)
        data: Optional external readings for persistence layer integration.
              Schema: [{"glucose_mg_dl": int, "timestamp": "ISO-8601"}, ...]
    """
    if data:
        readings = parse_external_data(data)
    else:
        minutes = max(1, min(1440, minutes))
        client = get_dexcom_client()
        readings = client.get_glucose_readings(minutes=minutes, max_count=288)
    
    if not readings:
        return {"status": "no_data", "message": "No readings available"}
    
    sorted_readings = sorted(readings, key=lambda r: r.datetime)
    
    episodes = []
    current_episode = None
    
    for reading in sorted_readings:
        value = reading.value
        
        if value < 54:
            episode_type = "very_low"
        elif value < low:
            episode_type = "low"
        elif value > 250:
            episode_type = "very_high"
        elif value > high:
            episode_type = "high"
        else:
            episode_type = None
        
        if episode_type:
            is_low = episode_type in ("low", "very_low")
            current_is_low = current_episode and current_episode["type"] in ("low", "very_low")
            
            if current_episode and is_low == current_is_low:
                current_episode["end"] = reading.datetime
                current_episode["values"].append(value)
                if episode_type in ("very_low", "very_high"):
                    current_episode["type"] = episode_type
            else:
                if current_episode:
                    episodes.append(current_episode)
                current_episode = {
                    "type": episode_type,
                    "start": reading.datetime,
                    "end": reading.datetime,
                    "values": [value],
                }
        else:
            if current_episode:
                episodes.append(current_episode)
                current_episode = None
    
    if current_episode:
        current_episode["ongoing"] = True
        episodes.append(current_episode)
    
    formatted = []
    for ep in episodes:
        duration = int((ep["end"] - ep["start"]).total_seconds() / 60)
        values = ep["values"]
        extreme = min(values) if ep["type"] in ("low", "very_low") else max(values)
        
        formatted.append({
            "type": ep["type"],
            "start": ep["start"].isoformat(),
            "end": ep["end"].isoformat(),
            "duration_minutes": max(duration, 5),
            "extreme_value": extreme,
            "mean_value": round(sum(values) / len(values), 1),
            "ongoing": ep.get("ongoing", False),
        })
    
    low_eps = [e for e in formatted if e["type"] in ("low", "very_low")]
    high_eps = [e for e in formatted if e["type"] in ("high", "very_high")]
    
    return {
        "readings_analyzed": len(sorted_readings),
        "episodes": formatted,
        "summary": {
            "total_episodes": len(formatted),
            "low_episodes": len(low_eps),
            "high_episodes": len(high_eps),
            "total_low_minutes": sum(e["duration_minutes"] for e in low_eps),
            "total_high_minutes": sum(e["duration_minutes"] for e in high_eps),
            "severe_lows": sum(1 for e in low_eps if e["type"] == "very_low"),
            "severe_highs": sum(1 for e in high_eps if e["type"] == "very_high"),
        }
    }
    
@mcp.tool()
def get_episode_details(
    minutes: int = 1440,
    low: int = 70,
    high: int = 180,
    data: list[dict] | None = None
) -> dict:
    """
    Get detailed context for each glucose episode - what led to it,
    how severe it was, and how recovery went.
    
    Args:
        minutes: Time period if using Dexcom API (1-1440, default 1440 = 24h)
        low: Low threshold in mg/dL (default 70)
        high: High threshold in mg/dL (default 180)
        data: Optional external readings for persistence layer integration.
    """
    if data:
        readings = parse_external_data(data)
    else:
        minutes = max(1, min(1440, minutes))
        client = get_dexcom_client()
        readings = client.get_glucose_readings(minutes=minutes, max_count=288)
    
    if not readings:
        return {"status": "no_data", "message": "No readings available"}
    
    points = sorted([(r.value, r.datetime) for r in readings], key=lambda x: x[1])
    
    # Find episodes
    episodes = []
    i = 0
    while i < len(points):
        value, dt = points[i]
        
        if value < low:
            ep_type = "very_low" if value < 54 else "low"
            is_low_episode = True
        elif value > high:
            ep_type = "very_high" if value > 250 else "high"
            is_low_episode = False
        else:
            i += 1
            continue
        
        start_idx = i
        episode_values = []
        while i < len(points):
            v = points[i][0]
            in_low = v < low
            in_high = v > high
            
            if (is_low_episode and not in_low) or (not is_low_episode and not in_high):
                break
            
            episode_values.append(points[i])
            if v < 54:
                ep_type = "very_low"
            elif v > 250:
                ep_type = "very_high"
            i += 1
        
        episodes.append({
            "type": ep_type,
            "start_idx": start_idx,
            "end_idx": i - 1,
            "values": episode_values,
            "is_low": is_low_episode,
        })
    
    # Analyze each episode
    detailed = []
    for ep in episodes:
        values = ep["values"]
        start_idx, end_idx = ep["start_idx"], ep["end_idx"]
        start_time, end_time = values[0][1], values[-1][1]
        glucose_values = [v for v, _ in values]
        
        # Find extreme point (nadir for lows, peak for highs)
        if ep["is_low"]:
            extreme = min(glucose_values)
            extreme_idx = glucose_values.index(extreme)
        else:
            extreme = max(glucose_values)
            extreme_idx = glucose_values.index(extreme)
        
        extreme_time = values[extreme_idx][1]
        duration = max(int((end_time - start_time).total_seconds() / 60), 5)
        
        # Lead-up (30 min before episode)
        leadup = points[max(0, start_idx - 6):start_idx]
        
        # Rate TO extreme (how fast did you spike/drop?)
        rate_to_extreme = None
        if extreme_idx > 0:
            t_diff = (extreme_time - start_time).total_seconds() / 60
            if t_diff > 0:
                v_diff = extreme - values[0][0]
                rate_to_extreme = round(v_diff / t_diff * 5, 1)  # per 5 min
        
        # Rate FROM extreme (how fast did you recover within episode?)
        rate_from_extreme = None
        if extreme_idx < len(values) - 1:
            t_diff = (end_time - extreme_time).total_seconds() / 60
            if t_diff > 0:
                v_diff = values[-1][0] - extreme
                rate_from_extreme = round(v_diff / t_diff * 5, 1)  # per 5 min
        
        # Recovery after episode (30 min after)
        recovery = points[end_idx + 1:min(len(points), end_idx + 7)]
        recovery_minutes = None
        recovery_rate = None
        overcorrection = None
        
        if recovery:
            # Time to get back in range
            for v, dt in recovery:
                if low <= v <= high:
                    recovery_minutes = int((dt - end_time).total_seconds() / 60)
                    break
            
            # Recovery rate after episode ended
            t_diff = (recovery[-1][1] - end_time).total_seconds() / 60
            if t_diff > 0:
                recovery_rate = round((recovery[-1][0] - values[-1][0]) / t_diff * 5, 1)
            
            # Overcorrection check
            recovery_values = [v for v, _ in recovery]
            if ep["is_low"] and max(recovery_values) > high:
                overcorrection = {"type": "rebound_high", "value": max(recovery_values)}
            elif not ep["is_low"] and min(recovery_values) < low:
                overcorrection = {"type": "overcorrect_low", "value": min(recovery_values)}
        
        detailed.append({
            "type": ep["type"],
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "duration_minutes": duration,
            "extreme_value": extreme,
            "extreme_time": extreme_time.isoformat(),
            "rate_to_extreme_per_5min": rate_to_extreme,
            "rate_from_extreme_per_5min": rate_from_extreme,
            "recovery_minutes": recovery_minutes,
            "recovery_rate_per_5min": recovery_rate,
            "overcorrection": overcorrection,
            "leadup_values": [v for v, _ in leadup],
        })
    
    return {
        "readings_analyzed": len(points),
        "episodes_analyzed": len(detailed),
        "episodes": detailed,
    }
    
@mcp.tool()
def analyze_time_blocks(
    minutes: int = 1440,
    low: int = 70,
    high: int = 180,
    data: list[dict] | None = None
) -> dict:
    """
    Analyze glucose by time of day - find when problems happen.
    
    Breaks down data into overnight (00-06), morning (06-12), 
    afternoon (12-18), and evening (18-24).
    
    Args:
        minutes: Time period if using Dexcom API (1-1440, default 1440 = 24h)
        low: Low threshold in mg/dL (default 70)
        high: High threshold in mg/dL (default 180)
        data: Optional external readings for persistence layer integration.
    """
    if data:
        readings = parse_external_data(data)
    else:
        minutes = max(1, min(1440, minutes))
        client = get_dexcom_client()
        readings = client.get_glucose_readings(minutes=minutes, max_count=288)
    
    if not readings:
        return {"status": "no_data", "message": "No readings available"}
    
    # Define time blocks
    blocks = {
        "overnight": {"range": "00:00-06:00", "readings": []},
        "morning": {"range": "06:00-12:00", "readings": []},
        "afternoon": {"range": "12:00-18:00", "readings": []},
        "evening": {"range": "18:00-24:00", "readings": []},
    }
    
    # Sort readings into blocks
    for r in readings:
        hour = r.datetime.hour
        value = r.value
        
        if 0 <= hour < 6:
            blocks["overnight"]["readings"].append(value)
        elif 6 <= hour < 12:
            blocks["morning"]["readings"].append(value)
        elif 12 <= hour < 18:
            blocks["afternoon"]["readings"].append(value)
        else:
            blocks["evening"]["readings"].append(value)
    
    # Analyze each block
    analyzed = {}
    best_block = None
    worst_block = None
    best_tir = -1
    worst_tir = 101
    
    for name, block in blocks.items():
        values = block["readings"]
        
        if not values:
            analyzed[name] = {
                "time_range": block["range"],
                "status": "no_data",
                "readings_count": 0,
            }
            continue
        
        avg = sum(values) / len(values)
        in_range = sum(1 for v in values if low <= v <= high)
        below = sum(1 for v in values if v < low)
        above = sum(1 for v in values if v > high)
        tir = round(in_range / len(values) * 100, 1)
        
        # Track best/worst
        if tir > best_tir:
            best_tir = tir
            best_block = name
        if tir < worst_tir:
            worst_tir = tir
            worst_block = name
        
        # Assessment
        if tir >= 80:
            assessment = "excellent"
        elif tir >= 70:
            assessment = "good"
        elif tir >= 50:
            assessment = "needs attention"
        else:
            assessment = "problematic"
        
        analyzed[name] = {
            "time_range": block["range"],
            "readings_count": len(values),
            "average_mg_dl": round(avg, 1),
            "min_mg_dl": min(values),
            "max_mg_dl": max(values),
            "time_in_range_percent": tir,
            "time_below_percent": round(below / len(values) * 100, 1),
            "time_above_percent": round(above / len(values) * 100, 1),
            "assessment": assessment,
        }
    
    return {
        "readings_analyzed": len(readings),
        "blocks": analyzed,
        "best_block": best_block,
        "worst_block": worst_block,
        "insight": f"Best control during {best_block} ({best_tir}% TIR), worst during {worst_block} ({worst_tir}% TIR)" if best_block and worst_block else None,
    }
    
@mcp.tool()
def check_alerts(
    urgent_low: int = 54,
    low: int = 70,
    high: int = 180,
    urgent_high: int = 250
) -> dict:
    """
    Check current glucose against alert thresholds.
    
    Simple threshold check for real-time alerting.
    
    Args:
        urgent_low: Urgent low threshold (default 54)
        low: Low threshold (default 70)
        high: High threshold (default 180)
        urgent_high: Urgent high threshold (default 250)
    """
    client = get_dexcom_client()
    reading = client.get_current_glucose_reading()
    
    if not reading:
        return {
            "status": "no_data",
            "message": "No current reading available",
            "alerts": [],
        }
    
    value = reading.value
    trend = reading.trend_direction
    alerts = []
    
    # Check thresholds
    if value < urgent_low:
        alerts.append({"level": "urgent", "type": "very_low", "message": f"Urgent low: {value} mg/dL"})
    elif value < low:
        alerts.append({"level": "warning", "type": "low", "message": f"Low: {value} mg/dL"})
    elif value > urgent_high:
        alerts.append({"level": "urgent", "type": "very_high", "message": f"Urgent high: {value} mg/dL"})
    elif value > high:
        alerts.append({"level": "warning", "type": "high", "message": f"High: {value} mg/dL"})
    
    # Trend alerts
    if trend in ("SingleDown", "DoubleDown") and value < 100:
        alerts.append({"level": "warning", "type": "falling_fast", "message": f"Falling fast at {value} mg/dL"})
    elif trend in ("SingleUp", "DoubleUp") and value > 150:
        alerts.append({"level": "warning", "type": "rising_fast", "message": f"Rising fast at {value} mg/dL"})
    
    return {
        "current_glucose": value,
        "trend": trend,
        "trend_arrow": reading.trend_arrow,
        "timestamp": reading.datetime.isoformat(),
        "has_alerts": len(alerts) > 0,
        "alert_count": len(alerts),
        "alerts": alerts,
        "status": "alert" if alerts else "ok",
    }
    
@mcp.tool()
def export_data(
    minutes: int = 1440,
    format: str = "json",
    data: list[dict] | None = None
) -> dict:
    """
    Export glucose readings for persistence layer integration.
    
    Returns clean, consistent data structure for storage in external databases.
    Call periodically to build long-term data history.
    
    Args:
        minutes: Time period to export (1-1440, default 1440 = 24h)
        format: Export format - "json" or "csv" (default "json")
        data: Optional external readings to format/export instead of fetching.
    """
    if data:
        readings = parse_external_data(data)
    else:
        minutes = max(1, min(1440, minutes))
        client = get_dexcom_client()
        readings = client.get_glucose_readings(minutes=minutes, max_count=288)
    
    if not readings:
        return {"status": "no_data", "message": "No readings to export"}
    
    # Consistent schema for persistence
    records = [
        {
            "glucose_mg_dl": r.value,
            "glucose_mmol_l": getattr(r, 'mmol_l', round(r.value / 18.0, 1)),
            "trend": getattr(r, 'trend_direction', None),
            "trend_arrow": getattr(r, 'trend_arrow', None),
            "timestamp": r.datetime.isoformat(),
        }
        for r in readings
    ]
    
    from datetime import datetime
    
    result = {
        "export_timestamp": datetime.now().isoformat(),
        "readings_count": len(records),
        "period_minutes": minutes if not data else None,
        "oldest_reading": records[-1]["timestamp"] if records else None,
        "newest_reading": records[0]["timestamp"] if records else None,
        "format": format,
        "readings": records,
    }
    
    if format == "csv":
        headers = ["timestamp", "glucose_mg_dl", "glucose_mmol_l", "trend", "trend_arrow"]
        csv_rows = [",".join(headers)]
        for r in records:
            csv_rows.append(f"{r['timestamp']},{r['glucose_mg_dl']},{r['glucose_mmol_l']},{r['trend']},{r['trend_arrow']}")
        result["csv"] = "\n".join(csv_rows)
    
    return result

@mcp.tool()
def get_agp_report(
    minutes: int = 1440,
    data: list[dict] | None = None
) -> dict:
    """
    Generate an Ambulatory Glucose Profile (AGP) report.
    
    AGP is the clinical standard used by endocrinologists. Shows glucose
    percentiles by time of day to identify patterns.
    
    Args:
        minutes: Time period if using Dexcom API (1-1440, default 1440 = 24h)
        data: Optional external readings for persistence layer integration.
    """
    if data:
        readings = parse_external_data(data)
    else:
        minutes = max(1, min(1440, minutes))
        client = get_dexcom_client()
        readings = client.get_glucose_readings(minutes=minutes, max_count=288)
    
    if not readings:
        return {"status": "no_data", "message": "No readings available"}
    
    # Group readings by hour
    hourly_values = {h: [] for h in range(24)}
    for r in readings:
        hourly_values[r.datetime.hour].append(r.value)
    
    def percentile(values: list, p: int) -> int | None:
        if not values:
            return None
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * p / 100)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]
    
    # Build hourly profile with percentiles
    hourly_profile = []
    for hour in range(24):
        values = hourly_values[hour]
        if values:
            hourly_profile.append({
                "hour": hour,
                "p5": percentile(values, 5),
                "p25": percentile(values, 25),
                "p50": percentile(values, 50),
                "p75": percentile(values, 75),
                "p95": percentile(values, 95),
                "readings_count": len(values),
            })
        else:
            hourly_profile.append({
                "hour": hour,
                "p5": None, "p25": None, "p50": None, "p75": None, "p95": None,
                "readings_count": 0,
            })
    
    # Overall stats
    all_values = [r.value for r in readings]
    avg = sum(all_values) / len(all_values)
    sd = stdev(all_values) if len(all_values) > 1 else 0
    cv = (sd / avg * 100) if avg > 0 else 0
    gmi = 3.31 + 0.02392 * avg
    
    in_range = sum(1 for v in all_values if 70 <= v <= 180)
    below_70 = sum(1 for v in all_values if v < 70)
    below_54 = sum(1 for v in all_values if v < 54)
    above_180 = sum(1 for v in all_values if v > 180)
    above_250 = sum(1 for v in all_values if v > 250)
    total = len(all_values)
    
    return {
        "report_type": "ambulatory_glucose_profile",
        "period_minutes": minutes,
        "readings_analyzed": total,
        
        "glucose_metrics": {
            "mean_mg_dl": round(avg, 1),
            "gmi_percent": round(gmi, 1),
            "cv_percent": round(cv, 1),
            "std_dev": round(sd, 1),
        },
        
        "time_in_ranges": {
            "very_low_below_54": round(below_54 / total * 100, 1),
            "low_54_70": round((below_70 - below_54) / total * 100, 1),
            "target_70_180": round(in_range / total * 100, 1),
            "high_180_250": round((above_180 - above_250) / total * 100, 1),
            "very_high_above_250": round(above_250 / total * 100, 1),
        },
        
        "clinical_targets": {
            "tir_target": ">70%",
            "tir_actual": round(in_range / total * 100, 1),
            "tbr_target": "<4%",
            "tbr_actual": round(below_70 / total * 100, 1),
            "cv_target": "<36%",
            "cv_actual": round(cv, 1),
        },
        
        "hourly_profile": hourly_profile,
    }  
    
def main():
    mcp.run()


if __name__ == "__main__":
    main()