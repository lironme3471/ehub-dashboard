"""
eHub Closed Won Dashboard generator.
Implements the full spec in copilot-instructions.md (Steps 1-5).

Usage:
    cd generate && source .venv/bin/activate
    python generate.py

Output: ../ehub-dashboard.html
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
import sys

from dotenv import load_dotenv
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed

load_dotenv()

SF_USERNAME       = os.environ["SF_USERNAME"]
SF_PASSWORD       = os.environ["SF_PASSWORD"]
SF_SECURITY_TOKEN = os.environ["SF_SECURITY_TOKEN"]
SF_DOMAIN         = os.environ.get("SF_DOMAIN", "login")
DASHBOARD_PW      = os.environ["DASHBOARD_PASSWORD"]

HERE      = pathlib.Path(__file__).parent
TEMPLATE  = HERE / "template.html"
OUTPUT    = HERE.parent / "ehub-dashboard.html"
TODAY     = datetime.date.today()
TODAY_STR = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# ---------------------------------------------------------------------------
# Static overrides — sourced from copilot-instructions.md Step 2
# ---------------------------------------------------------------------------

FORCE_EXCLUDE: set[str] = {
    "006Ui00000nwNJNIA2",  # OneMain PRIMARY
    "006Hu00001V1zjUIAR",  # Palace Resorts
    "006Ui0000279WjZIAU",  # Swinton / Markerstudy
    "006Ui00002ITdIjIAL",  # THE AA internal allocation "DO NOT CONTRACT"
    "006Ui00000pY77IIAS",  # ANZ Bank Australia Cloud Recording split
    "0063n000010m4BwAAI",  # DWP UK Enterprise CCaaS
}

FORCE_INCLUDE_IDS: list[str] = [
    "006Ui00002JQIdFIAX", "006Ui00001FlFCAIA3", "006Ui00000uEyNRIA0",
    "006Ui00001AmVpfIAF", "006Hu00001XhMB1IAN", "0063n000010laAfAAI",
    "006Ui00001kd7Q1IAI", "006Ui000026cAebIAE", "006Ui00002Sw43hIAB",
    "006Ui00000aTVuwIAG", "006Ui00000GdYi9IAF", "006Ui00000rHB6zIAG",
    "006Ui00001waBEMIA2", "006Ui00001IeBmfIAF", "006Ui00002Btqt5IAB",
    "006Ui00002KscTaIAJ",
]

FORCE_OFFLINE: set[str] = {
    "006Ui00002JQIdFIAX", "006Ui00001FlFCAIA3", "0063n000010laAfAAI",
    "006Ui00001kd7Q1IAI", "006Ui000026cAebIAE", "006Ui00002Sw43hIAB",
    "006Ui00000aTVuwIAG", "006Ui00002Btqt5IAB", "006Ui00002KscTaIAJ",
}

FORCE_RT: set[str] = {
    "006Ui00000uEyNRIA0", "006Ui00001AmVpfIAF", "006Hu00001XhMB1IAN",
    "006Ui00000GdYi9IAF", "006Ui00000rHB6zIAG", "006Ui00001waBEMIA2",
    "006Ui00001IeBmfIAF",
}

FORCE_SMARTREACH: set[str] = {
    "006Ui0000226yLtIAI", "006Ui000029nDfRIAU", "006Ui00002H5zzQIAR",
    "006Ui00001wt5upIAA", "006Ui00001BopzlIAB", "006Ui00001eiPHjIAM",
    "006Ui00000vVOQDIA4", "006Ui00002JQIdFIAX", "006Ui00001tv9XqIAI",
    "0063n000010laAfAAI", "006Ui00001kd7Q1IAI", "006Ui000026cAebIAE",
    "006Ui00002Sw43hIAB", "006Ui00000aTVuwIAG", "006Ui00002Btqt5IAB",
}

FORCE_TICKETING: set[str] = {
    "006Ui00001wt5upIAA", "006Ui00001K1hWjIAJ", "006Ui00001FlFCAIA3",
}

MANUAL_GL: dict[str, tuple] = {
    "006Ui0000226yLtIAI": ("Live",                  "gl-live",    None),
    "006Ui00002Sw43hIAB": ("Live",                  "gl-live",    None),
    "006Ui00002JQIdFIAX": ("ETA \u2192 2026-10-08", "gl-eta",     "2026-10-08"),
    "006Ui00000uEyNRIA0": ("ETA \u2192 2026-08-10", "gl-eta",     "2026-08-10"),
    "006Ui00000hp5eQIAQ": ("ETA \u2192 2026-09-04", "gl-eta",     "2026-09-04"),
    "006Ui000026cAebIAE": ("ETA \u2192 2026-11-27", "gl-eta",     "2026-11-27"),
    "006Ui000012MCldIAG": ("ETA \u2192 2026-08-31", "gl-eta",     "2026-08-31"),
    "006Ui00002KscTaIAJ": ("ETA \u2192 2027-07-23", "gl-eta",     "2027-07-23"),
}

AGENT_OVERRIDES: dict[str, int] = {"006Ui00002KscTaIAJ": 200}
REGION_OVERRIDES: dict[str, str] = {"006Ui00001kd7Q1IAI": "Americas"}

ACCT_CLEANUPS: list[tuple] = [
    ("MINISTERE DU REVENU DU QUEBEC - CANADA - ENTERPRISEC",
     "MINISTERE DU REVENU DU QUEBEC"),
    ("WNS GLOBAL SERVICES (P) LTD - TOKYU BU",
     "WNS GLOBAL SERVICES - TOKYO BU"),
    ("WNS GLOBAL SERVICES (P) LTD - INDIA - HQ",
     "WNS GLOBAL SERVICES - INDIA HQ"),
    ("LOWE\u2019S COMPANIES, INC.", "LOWE'S COMPANIES, INC."),
    ("AMERICAN NATIONAL INSURANCE COMPANY INC (ANICO)",
     "AMERICAN NATIONAL INSURANCE COMPANY INC"),
]

INTEG_COLORS = {"SmartReach": "#FF8A00", "Ticketing": "#6100FF", "AMC": "#1F9D57"}
SKU_INTEG    = {"610346-3070": "SmartReach", "610346-3071": "Ticketing", "610347-3268": "AMC"}
HUB_COLORS   = {"Real-Time": "#3694FC", "Offline": "#36EAD0", "RT + Offline": "#6100FF"}

IGNORE_IDS: set[str] = {
    "006Ui00001OnM98IAF",
    "006Ui00001iARDBIA4",
    "006Ui00001dgksIIAQ",
}

_OPP_FIELDS = """Id, Name, CloseDate, Total_ACV_Value__c, CurrencyIsoCode,
    Account.Name, Account.Top_Parent_Account__r.Name,
    Owner.Name, Sales_Region__c, Opportunity_Agent_Count__c,
    Expected_Go_Live__c, PM_Go_Live_Date__c, PM_Estimated_Go_Live__c,
    Contract_Type__c, NICE_OM_Booked__c, TimetoTurnUp__c"""

OPP_SOQL = f"""
    SELECT {_OPP_FIELDS}
    FROM Opportunity
    WHERE (StageName LIKE '%Closed%Won%' OR StageName LIKE '%WFO%Won%')
      AND Id IN (
        SELECT OpportunityId FROM OpportunityLineItem
        WHERE PricebookEntry.Product2.Name LIKE '%Engagement Hub%'
          AND (NOT PricebookEntry.Product2.Name LIKE '%Setup%')
          AND (NOT PricebookEntry.Product2.Name LIKE '%implementation%')
          AND (
            (TotalPrice > 0 AND PricebookEntry.Product2.ProductCode != '1464-3063-XXX')
            OR (PricebookEntry.Product2.ProductCode = '1464-3063-XXX' AND Quantity > 1)
          )
      )
      AND Total_ACV_Value__c > 0
      AND Account.Name != 'MAIN LINE HEALTH'
      AND Account.Name != 'PERMANENT GENERAL ASSURANCE CORPORATION - ENTERPRISE'
      AND Account.Name != 'OHIO PUBLIC EMPLOYEES RETIREMENT SYSTEM - UPTIVITY'
    ORDER BY CloseDate DESC LIMIT 200
"""


def _q(ids):
    return ",".join(f"'{i}'" for i in ids)


def _fetch_projects(sf, ids):
    proj_map = {}
    try:
        for r in sf.query_all(f"""
            SELECT Opportunity__c, Status__c, PSActualGoLive__c,
                   PSEstimatedGoLive__c, Estimated_Project_End__c
            FROM Project__c
            WHERE RecordType.Name = 'PS Parent Project - SaaS'
              AND Opportunity__c IN ({_q(ids)}) LIMIT 400
        """)["records"]:
            oid = r["Opportunity__c"]
            ex  = proj_map.get(oid)
            if not ex or (r.get("PSActualGoLive__c") and not ex.get("PSActualGoLive__c")):
                proj_map[oid] = r
    except Exception as e:
        print(f"  WARNING: project query failed ({type(e).__name__}): {e}")
    return proj_map


def _fetch_hub_sets(sf, ids):
    offline, rt = set(), set()
    id_str = _q(ids)
    try:
        for r in sf.query_all(f"""
            SELECT OpportunityId FROM OpportunityLineItem
            WHERE PricebookEntry.Product2.ProductCode = '1464-3063-XXX'
              AND Quantity > 1 AND OpportunityId IN ({id_str}) LIMIT 200
        """)["records"]:
            offline.add(r["OpportunityId"])
    except Exception as e:
        print(f"  WARNING: offline SKU query failed: {e}")
    try:
        for r in sf.query_all(f"""
            SELECT OpportunityId FROM OpportunityLineItem
            WHERE PricebookEntry.Product2.Name LIKE '%Engagement Hub%Real-Time%'
              AND TotalPrice > 0 AND OpportunityId IN ({id_str}) LIMIT 200
        """)["records"]:
            rt.add(r["OpportunityId"])
    except Exception as e:
        print(f"  WARNING: RT SKU query failed: {e}")
    return offline, rt


def _fetch_integ_map(sf, ids):
    integ_map = {}
    try:
        for r in sf.query_all(f"""
            SELECT OpportunityId, PricebookEntry.Product2.ProductCode
            FROM OpportunityLineItem
            WHERE (PricebookEntry.Product2.ProductCode LIKE '610346-3070-%'
                OR PricebookEntry.Product2.ProductCode LIKE '610346-3071-%'
                OR PricebookEntry.Product2.ProductCode LIKE '610347-3268-%')
              AND OpportunityId IN ({_q(ids)}) LIMIT 200
        """)["records"]:
            oid  = r["OpportunityId"]
            code = ((r.get("PricebookEntry") or {}).get("Product2") or {}).get("ProductCode") or ""
            for prefix, badge in SKU_INTEG.items():
                if code.startswith(prefix):
                    integ_map.setdefault(oid, set()).add(badge)
    except Exception as e:
        print(f"  WARNING: integration SKU query failed: {e}")
    return integ_map


def _detect_candidates(sf, dashboard_ids):
    candidates = []
    try:
        for r in sf.query_all("""
            SELECT Id, Name, CloseDate, Total_ACV_Value__c, CurrencyIsoCode,
                   Account.Name, Owner.Name
            FROM Opportunity
            WHERE (StageName LIKE '%Closed%Won%' OR StageName LIKE '%WFO%Won%')
              AND CloseDate = LAST_N_DAYS:60
              AND Account.Name != 'MAIN LINE HEALTH'
              AND Account.Name != 'PERMANENT GENERAL ASSURANCE CORPORATION - ENTERPRISE'
              AND Account.Name != 'OHIO PUBLIC EMPLOYEES RETIREMENT SYSTEM - UPTIVITY'
              AND Id IN (
                SELECT OpportunityId FROM OpportunityLineItem
                WHERE PricebookEntry.Product2.ProductCode LIKE '610346-3070-%'
                   OR PricebookEntry.Product2.ProductCode LIKE '610346-3071-%'
                   OR PricebookEntry.Product2.ProductCode LIKE '610347-3268-%'
                   OR (PricebookEntry.Product2.ProductCode = '1464-3063-XXX' AND Quantity > 1)
              ) LIMIT 100
        """)["records"]:
            oid = r["Id"]
            if oid not in dashboard_ids and oid not in IGNORE_IDS and oid not in FORCE_EXCLUDE:
                candidates.append(r)
    except Exception as e:
        print(f"  WARNING: candidate detection failed: {e}")
    return candidates


def _clean_acct(name):
    for old, new in ACCT_CLEANUPS:
        if name == old:
            return new
    return name


def _classify_gl(oid, om_booked, ttt, proj, pm_go_live, pm_est, exp_go_live):
    if oid in MANUAL_GL:
        return MANUAL_GL[oid]

    proj_status = proj.get("Status__c") or ""
    proj_actual = proj.get("PSActualGoLive__c")
    proj_est    = proj.get("PSEstimatedGoLive__c")
    proj_end    = proj.get("Estimated_Project_End__c")

    def days(s):
        return (datetime.date.fromisoformat(s) - TODAY).days if s else None

    # Step 1
    if om_booked and ttt is not None:
        return "Live", "gl-live", None
    # Step 2
    end_days = days(proj_end)
    if ttt is not None and (end_days is None or end_days <= 30):
        return "Live", "gl-live", None
    # Step 3
    if proj_status == "2 - Closed" and proj_actual and ttt is not None:
        return "Live", "gl-live", None
    # Step 4
    if end_days is not None and end_days > 30:
        return f"Delayed \u2192 {proj_end}", "gl-delayed", proj_end
    # Step 5-6: ETA waterfall
    eta = proj_est or pm_est or exp_go_live
    if eta:
        d = datetime.date.fromisoformat(eta)
        if d < TODAY:
            return f"Delayed \u2192 {eta}", "gl-delayed", eta
        return f"ETA \u2192 {eta}", "gl-eta", eta
    # pm_go_live as final live check
    if pm_go_live:
        d = datetime.date.fromisoformat(pm_go_live)
        if d <= TODAY:
            return "Live", "gl-live", None
        return f"ETA \u2192 {pm_go_live}", "gl-eta", pm_go_live
    return "TBD", "gl-tbd", None


def _build_row(o, proj, offline_ids, rt_ids, integ_map):
    oid = o["Id"]
    acct_rec  = o.get("Account") or {}
    acct_name = _clean_acct(acct_rec.get("Name") or "")
    parent    = (acct_rec.get("Top_Parent_Account__r") or {}).get("Name") or ""
    group     = _clean_acct(parent) if parent else acct_name or "Unknown"

    is_off = oid in offline_ids or oid in FORCE_OFFLINE
    is_rt  = oid in rt_ids      or oid in FORCE_RT
    if is_off and is_rt:
        hub, hubcolor = "RT + Offline", HUB_COLORS["RT + Offline"]
    elif is_off:
        hub, hubcolor = "Offline",      HUB_COLORS["Offline"]
    else:
        hub, hubcolor = "Real-Time",    HUB_COLORS["Real-Time"]

    badges = set(integ_map.get(oid, set()))
    if oid in FORCE_SMARTREACH:
        badges.add("SmartReach")
    if oid in FORCE_TICKETING:
        badges.add("Ticketing")
    integ = [[b, INTEG_COLORS[b]] for b in sorted(badges) if b in INTEG_COLORS]

    gl, glcls, glsort = _classify_gl(
        oid,
        om_booked  = bool(o.get("NICE_OM_Booked__c")),
        ttt        = o.get("TimetoTurnUp__c"),
        proj       = proj,
        pm_go_live = o.get("PM_Go_Live_Date__c"),
        pm_est     = o.get("PM_Estimated_Go_Live__c"),
        exp_go_live= o.get("Expected_Go_Live__c"),
    )

    agents = AGENT_OVERRIDES.get(oid)
    if agents is None:
        raw = o.get("Opportunity_Agent_Count__c")
        agents = int(raw) if raw is not None else None

    name = o["Name"]
    name = re.sub(r'IC24-\s+CCaaS', 'IC24 - CCaaS', name)
    if oid == "006Ui00001FlFCAIA3":
        name = "Accurate Background | CXone QMA"

    owner = (o.get("Owner") or {}).get("Name") or ""
    owner = owner.replace("Adam Massingberd - Mundy", "Adam Massingberd-Mundy")

    region = REGION_OVERRIDES.get(oid) or o.get("Sales_Region__c") or ""

    return {
        "id": oid, "acct": acct_name, "name": name,
        "type": o.get("Contract_Type__c") or "",
        "integ": integ, "hub": hub, "hubcolor": hubcolor,
        "close": o["CloseDate"],
        "acv": o.get("Total_ACV_Value__c"),
        "cur": o.get("CurrencyIsoCode") or "USD",
        "agents": agents, "region": region,
        "gl": gl, "glcls": glcls, "glsort": glsort,
        "owner": owner, "group": group,
    }


def main():
    print(f"eHub dashboard generator — {TODAY_STR}")

    print("Authenticating to Salesforce …")
    try:
        sf = Salesforce(username=SF_USERNAME, password=SF_PASSWORD,
                        security_token=SF_SECURITY_TOKEN, domain=SF_DOMAIN)
    except SalesforceAuthenticationFailed as exc:
        sys.exit(f"Salesforce auth failed: {exc}")

    print("  Query 1 — main eHub opportunities …")
    q1 = sf.query_all(OPP_SOQL)["records"]
    print(f"  → {len(q1)} records")

    print("  Query 1b — force-include deals …")
    q1b = sf.query_all(
        f"SELECT {_OPP_FIELDS} FROM Opportunity WHERE Id IN ({_q(FORCE_INCLUDE_IDS)}) LIMIT 20"
    )["records"]
    print(f"  → {len(q1b)} force-include records")

    seen: dict[str, dict] = {}
    for r in q1b:
        seen[r["Id"]] = r
    for r in q1:
        if r["Id"] not in seen:
            seen[r["Id"]] = r
    for ex in FORCE_EXCLUDE:
        seen.pop(ex, None)

    all_ids = list(seen.keys())
    print(f"  Final pool after excludes: {len(all_ids)} deals")

    print("  Query 2 — PS parent projects …")
    proj_map = _fetch_projects(sf, all_ids)
    print(f"  → {len(proj_map)} project records")

    print("  Queries 3+4 — hub SKU sets …")
    offline_ids, rt_ids = _fetch_hub_sets(sf, all_ids)
    print(f"  → offline={len(offline_ids)} rt={len(rt_ids)}")

    print("  Query 5 — integration badges …")
    integ_map = _fetch_integ_map(sf, all_ids)
    print(f"  → {len(integ_map)} opps with integration lines")

    rows = [_build_row(o, proj_map.get(o["Id"], {}), offline_ids, rt_ids, integ_map)
            for o in seen.values()]

    grp_recent = {}
    for r in rows:
        g = r["group"]
        if g not in grp_recent or r["close"] > grp_recent[g]:
            grp_recent[g] = r["close"]

    data = {"rows": rows, "grp_recent": grp_recent}

    live    = sum(1 for r in rows if r["glcls"] == "gl-live")
    delayed = sum(1 for r in rows if r["glcls"] == "gl-delayed")
    eta     = sum(1 for r in rows if r["glcls"] == "gl-eta")
    tbd     = sum(1 for r in rows if r["glcls"] == "gl-tbd")
    usd_acv = sum(r["acv"] or 0 for r in rows if r["cur"] == "USD")
    print(f"\nSanity: {len(rows)} deals — Live:{live} Delayed:{delayed} ETA:{eta} TBD:{tbd}  USD ACV:${usd_acv:,.0f}")

    if not (45 <= len(rows) <= 60):
        print(f"  *** WARNING: deal count {len(rows)} outside expected 45-60 ***")

    present = {r["id"] for r in rows}
    missing = [i for i in FORCE_INCLUDE_IDS if i not in present]
    if missing:
        print(f"  *** WARNING: missing force-includes: {missing} ***")

    print("\n  Candidate detection (last 60 days) …")
    candidates = _detect_candidates(sf, present)
    if candidates:
        print(f"\n{'='*60}")
        print(f"NEW DEAL CANDIDATES — {len(candidates)} awaiting triage:")
        for c in candidates:
            acct = (c.get("Account") or {}).get("Name", "")
            print(f"  *** NEW DEAL CANDIDATE — awaiting triage ***")
            print(f"      Account : {acct}")
            print(f"      Deal    : {c['Name']}")
            print(f"      Close   : {c['CloseDate']}")
            print(f"      ACV     : {c.get('CurrencyIsoCode','')} {c.get('Total_ACV_Value__c')}")
            print(f"      SF link : https://niceincontact.lightning.force.com/lightning/r/Opportunity/{c['Id']}/view")
        print(f"{'='*60}\n")
    else:
        print("  → No new candidates.")

    pending = "006Ui00002Y6K5xIAF"
    if pending not in present:
        print(f"\n  Pending triage: {pending} — RINGCENTRAL CC SE1 B32 OSH Amendment (Ticketing SKU, closed 2026-07-30)")

    pw_hash = hashlib.sha256(DASHBOARD_PW.encode()).hexdigest()
    print(f"\nRendering template → {OUTPUT} …")
    tmpl = TEMPLATE.read_text(encoding="utf-8")
    html = (tmpl
            .replace("%%DATE%%",    TODAY_STR)
            .replace("%%PW_HASH%%", pw_hash)
            .replace("%%DATA%%",    json.dumps(data, separators=(",", ":"))))
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Done. Output: {OUTPUT.resolve()}")


if __name__ == "__main__":
    main()
