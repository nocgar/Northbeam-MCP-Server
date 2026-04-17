#!/usr/bin/env python3
import csv
import io
import json
import os
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from pathlib import Path

# Load .env from same directory as this script
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

NORTHBEAM_AUTH = "Basic e2b802f3-dc6d-40a1-8c22-9266eb9f064a"
NORTHBEAM_CLIENT_ID = "18a4cb73-437d-4549-9121-683ccfb8a046"
SLACK_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_USER = "U0ADC5936"


def slack_dm(message):
    data = json.dumps({"channel": SLACK_USER, "text": message}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=data,
        headers={"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def northbeam_request(method, path, body=None):
    url = f"https://api.northbeam.io/v1/exports/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": NORTHBEAM_AUTH,
            "Data-Client-ID": NORTHBEAM_CLIENT_ID,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fmt_dollar(v):
    return f"${v:,.2f}"


def fmt_roas(v):
    return f"{v:.2f}x"


# STEP 1: Create export
try:
    result = northbeam_request("POST", "data-export", {
        "metrics": [
            {"id": "spend"}, {"id": "rev"}, {"id": "roas"}, {"id": "txns"},
            {"id": "cac"}, {"id": "customersFt"}, {"id": "customersRtn"}
        ],
        "attribution_options": {
            "attribution_models": ["northbeam_custom"],
            "attribution_windows": ["1"],
            "accounting_modes": ["accrual"]
        },
        "level": "platform",
        "time_granularity": "DAILY",
        "period_type": "LAST_7_DAYS",
        "breakdowns": [{"key": "Platform (Northbeam)", "values": [
            "Facebook Ads", "Google Ads", "TikTok", "Snapchat Ads", "Pinterest", "Klaviyo"
        ]}]
    })
    export_id = result["id"]
except Exception as e:
    slack_dm(f"Northbeam Daily Report FAILED: Could not create data export. Error: {e}")
    sys.exit(1)

# STEP 2: Poll for result
csv_url = None
for attempt in range(6):
    time.sleep(5)
    try:
        poll = northbeam_request("GET", f"data-export/result/{export_id}")
        if poll.get("status") == "SUCCESS":
            csv_url = poll["result"][0]
            break
        if attempt == 5:
            slack_dm(f"Northbeam Daily Report FAILED: Export did not complete. Status: {poll.get('status')}")
            sys.exit(1)
    except Exception as e:
        if attempt == 5:
            slack_dm(f"Northbeam Daily Report FAILED: Error polling export. Error: {e}")
            sys.exit(1)

# STEP 3: Download and parse CSV
try:
    with urllib.request.urlopen(csv_url) as resp:
        content = resp.read().decode("utf-8")

    totals = defaultdict(lambda: defaultdict(float))
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        platform = row.get("breakdown_platform_northbeam", "Unknown")
        for key in ["spend", "rev", "transactions", "customers_new", "customers_returning"]:
            val = row.get(key, "")
            if val:
                try:
                    totals[platform][key] += float(val)
                except ValueError:
                    pass
except Exception as e:
    slack_dm(f"Northbeam Daily Report FAILED: Could not download or parse CSV. Error: {e}")
    sys.exit(1)

# STEP 4: Build and send Slack message
try:
    lines = ["*Pit Viper - Northbeam Daily Performance Report (Last 7 Days)*",
             "Attribution: Clicks Only | 1-day window | Accrual", ""]

    grand = defaultdict(float)

    for platform, data in sorted(totals.items()):
        spend = data["spend"]
        rev = data["rev"]
        if spend == 0 and rev == 0:
            continue
        txns = data["transactions"]
        new_c = data["customers_new"]
        ret_c = data["customers_returning"]
        roas = rev / spend if spend > 0 else 0
        cac = spend / (new_c + ret_c) if (new_c + ret_c) > 0 else 0

        for k, v in data.items():
            grand[k] += v

        lines.append(f"*{platform}*")
        lines.append(f"Spend: {fmt_dollar(spend)} | Revenue: {fmt_dollar(rev)} | ROAS: {fmt_roas(roas)}")
        lines.append(f"Transactions: {int(txns)} | New Customers: {int(new_c)} | Returning: {int(ret_c)} | CAC: {fmt_dollar(cac)}")
        lines.append("")

    g_spend = grand["spend"]
    g_rev = grand["rev"]
    g_txns = grand["transactions"]
    g_new = grand["customers_new"]
    g_ret = grand["customers_returning"]
    g_roas = g_rev / g_spend if g_spend > 0 else 0
    g_cac = g_spend / (g_new + g_ret) if (g_new + g_ret) > 0 else 0

    lines.append("*Totals*")
    lines.append(f"Spend: {fmt_dollar(g_spend)} | Revenue: {fmt_dollar(g_rev)} | ROAS: {fmt_roas(g_roas)}")
    lines.append(f"Transactions: {int(g_txns)} | New: {int(g_new)} | Returning: {int(g_ret)} | CAC: {fmt_dollar(g_cac)}")
    lines.append("")
    lines.append("Source: Northbeam Data Export API (1-day click attribution)")

    slack_dm("\n".join(lines))
except Exception as e:
    slack_dm(f"Northbeam Daily Report FAILED: Could not format or send report. Error: {e}")
    sys.exit(1)
