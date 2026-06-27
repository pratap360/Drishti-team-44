#!/usr/bin/env python3
"""
DRISHTI Kumbh Finder — Final Results Generator
Processes all datasets and produces comprehensive analysis results.
"""

import csv
import json
import os
import math
from collections import Counter, defaultdict
from datetime import datetime
from rapidfuzz import fuzz

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def load_csv(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


print("=" * 70)
print("DRISHTI KUMBH FINDER — FINAL ANALYSIS RESULTS")
print("=" * 70)

# ─── Load all datasets ───────────────────────────────────────────────
persons = load_csv("Synthetic_Missing_Persons_2500.csv")
cctv = load_csv("CCTV_Locations.csv")
zones = load_csv("Zone_Boundaries.csv")
police = load_csv("Police_Stations.csv")
chokepoints = load_csv("Chokepoints_Parking.csv")

print(f"\nDatasets loaded:")
print(f"  Missing Persons:  {len(persons):,} records")
print(f"  CCTV Cameras:     {len(cctv):,} cameras")
print(f"  Zones:            {len(zones):,} zones")
print(f"  Police Stations:  {len(police):,} stations")
print(f"  Chokepoints:      {len(chokepoints):,} points")

# ─── 1. MISSING PERSONS ANALYSIS ─────────────────────────────────────
print("\n" + "=" * 70)
print("1. MISSING PERSONS — STATUS BREAKDOWN")
print("=" * 70)

status_counts = Counter(p["status"] for p in persons)
total = len(persons)
for status, count in status_counts.most_common():
    pct = count / total * 100
    print(f"  {status:<30} {count:>5}  ({pct:.1f}%)")

reunited = status_counts.get("Reunited", 0)
pending = status_counts.get("Pending", 0)
unresolved = status_counts.get("Unresolved", 0)
hospital = status_counts.get("Transferred to hospital", 0)

print(f"\n  Reunification Rate:  {reunited/total*100:.1f}%")
print(f"  Still Pending:       {pending/total*100:.1f}%")
print(f"  Unresolved:          {unresolved/total*100:.1f}%")

# ─── 2. RESOLUTION TIME ANALYSIS ─────────────────────────────────────
print("\n" + "=" * 70)
print("2. RESOLUTION TIME ANALYSIS")
print("=" * 70)

resolution_hours = [float(p["resolution_hours"]) for p in persons if p["resolution_hours"]]
if resolution_hours:
    avg_hours = sum(resolution_hours) / len(resolution_hours)
    median_hours = sorted(resolution_hours)[len(resolution_hours) // 2]
    min_hours = min(resolution_hours)
    max_hours = max(resolution_hours)
    under_1h = sum(1 for h in resolution_hours if h <= 1)
    under_6h = sum(1 for h in resolution_hours if h <= 6)
    under_24h = sum(1 for h in resolution_hours if h <= 24)
    over_48h = sum(1 for h in resolution_hours if h > 48)

    print(f"  Records with resolution data:  {len(resolution_hours):,}")
    print(f"  Average resolution time:       {avg_hours:.1f} hours")
    print(f"  Median resolution time:        {median_hours:.1f} hours")
    print(f"  Fastest resolution:            {min_hours:.1f} hours")
    print(f"  Slowest resolution:            {max_hours:.1f} hours")
    print(f"\n  Resolved within 1 hour:        {under_1h:>5} ({under_1h/len(resolution_hours)*100:.1f}%)")
    print(f"  Resolved within 6 hours:       {under_6h:>5} ({under_6h/len(resolution_hours)*100:.1f}%)")
    print(f"  Resolved within 24 hours:      {under_24h:>5} ({under_24h/len(resolution_hours)*100:.1f}%)")
    print(f"  Took over 48 hours:            {over_48h:>5} ({over_48h/len(resolution_hours)*100:.1f}%)")

# ─── 3. AGE BAND ANALYSIS ────────────────────────────────────────────
print("\n" + "=" * 70)
print("3. AGE BAND DISTRIBUTION")
print("=" * 70)

age_counts = Counter(p["age_band"] for p in persons)
age_order = ["0-12", "13-17", "18-40", "41-60", "61-70", "71-80", "80+"]
for age in age_order:
    count = age_counts.get(age, 0)
    pct = count / total * 100
    bar = "█" * int(pct)
    print(f"  {age:<8} {count:>5}  ({pct:>5.1f}%)  {bar}")

most_vulnerable = age_counts.most_common(1)[0]
print(f"\n  Most vulnerable group: {most_vulnerable[0]} ({most_vulnerable[1]} cases, {most_vulnerable[1]/total*100:.1f}%)")

# ─── 4. GENDER ANALYSIS ──────────────────────────────────────────────
print("\n" + "=" * 70)
print("4. GENDER DISTRIBUTION")
print("=" * 70)

gender_counts = Counter(p["gender"] for p in persons)
for gender, count in gender_counts.most_common():
    pct = count / total * 100
    print(f"  {gender:<12} {count:>5}  ({pct:.1f}%)")

# Gender x Status cross-tab
gender_status = defaultdict(Counter)
for p in persons:
    gender_status[p["gender"]][p["status"]] += 1

print("\n  Reunification rate by gender:")
for gender in ["Male", "Female", "Unknown"]:
    gs = gender_status[gender]
    g_total = sum(gs.values())
    g_reunited = gs.get("Reunited", 0)
    if g_total > 0:
        print(f"    {gender:<12} {g_reunited}/{g_total}  ({g_reunited/g_total*100:.1f}%)")

# ─── 5. REPORTING CENTER ANALYSIS ────────────────────────────────────
print("\n" + "=" * 70)
print("5. REPORTING CENTER ANALYSIS")
print("=" * 70)

center_counts = Counter(p["reporting_center"] for p in persons)
center_reunited = Counter()
center_resolution = defaultdict(list)
for p in persons:
    if p["status"] == "Reunited":
        center_reunited[p["reporting_center"]] += 1
    if p["resolution_hours"]:
        center_resolution[p["reporting_center"]].append(float(p["resolution_hours"]))

print(f"  Total centers: {len(center_counts)}")
print(f"\n  {'Center':<40} {'Cases':>6} {'Reunited':>9} {'Rate':>7} {'Avg Hrs':>8}")
print(f"  {'-'*40} {'-'*6} {'-'*9} {'-'*7} {'-'*8}")

for center, count in center_counts.most_common():
    r = center_reunited.get(center, 0)
    rate = r / count * 100 if count > 0 else 0
    avg_h = sum(center_resolution[center]) / len(center_resolution[center]) if center_resolution[center] else 0
    print(f"  {center:<40} {count:>6} {r:>9} {rate:>6.1f}% {avg_h:>7.1f}")

# ─── 6. TEMPORAL ANALYSIS ────────────────────────────────────────────
print("\n" + "=" * 70)
print("6. TEMPORAL PATTERNS (Daily Case Volume)")
print("=" * 70)

date_counts = Counter()
hour_counts = Counter()
for p in persons:
    if p["reported_at"]:
        try:
            dt = datetime.strptime(p["reported_at"], "%Y-%m-%d %H:%M")
            date_counts[dt.strftime("%Y-%m-%d")] += 1
            hour_counts[dt.hour] += 1
        except ValueError:
            pass

sorted_dates = sorted(date_counts.items())
avg_daily = total / len(date_counts) if date_counts else 0
peak_date, peak_count = max(date_counts.items(), key=lambda x: x[1]) if date_counts else ("", 0)

print(f"  Date range:      {sorted_dates[0][0]} to {sorted_dates[-1][0]}")
print(f"  Total days:      {len(date_counts)}")
print(f"  Average/day:     {avg_daily:.1f}")
print(f"  Peak day:        {peak_date} ({peak_count} cases)")
print(f"  Peak/Avg ratio:  {peak_count/avg_daily:.1f}x (Amrit Snan spike)")

print(f"\n  Top 10 busiest days:")
for date, count in sorted(date_counts.items(), key=lambda x: -x[1])[:10]:
    bar = "█" * (count // 3)
    print(f"    {date}  {count:>4} cases  {bar}")

print(f"\n  Hourly distribution (peak hours):")
for hour in sorted(hour_counts.keys()):
    count = hour_counts[hour]
    bar = "█" * (count // 5)
    print(f"    {hour:02d}:00  {count:>4}  {bar}")

# ─── 7. DATA QUALITY ─────────────────────────────────────────────────
print("\n" + "=" * 70)
print("7. DATA QUALITY ASSESSMENT")
print("=" * 70)

no_name = sum(1 for p in persons if not p["missing_person_name"].strip())
no_mobile = sum(1 for p in persons if not p["reporter_mobile"].strip())
no_desc = sum(1 for p in persons if not p["physical_description"].strip())
duplicates = sum(1 for p in persons if p["is_duplicate_report"] == "True")

print(f"  Missing name:              {no_name:>5}  ({no_name/total*100:.1f}%)")
print(f"  Missing reporter mobile:   {no_mobile:>5}  ({no_mobile/total*100:.1f}%)")
print(f"  Missing description:       {no_desc:>5}  ({no_desc/total*100:.1f}%)")
print(f"  Duplicate reports:         {duplicates:>5}  ({duplicates/total*100:.1f}%)")
print(f"  Completely anonymous:      {sum(1 for p in persons if not p['missing_person_name'].strip() and not p['reporter_mobile'].strip()):>5}")

# ─── 8. DUPLICATE DETECTION (fuzzy matching) ─────────────────────────
print("\n" + "=" * 70)
print("8. CROSS-CENTER DUPLICATE DETECTION (Fuzzy Matching)")
print("=" * 70)

pending_persons = [p for p in persons if p["status"] in ("Pending", "Unresolved") and p["missing_person_name"].strip()]
dup_groups = []
seen = set()

for i, p in enumerate(pending_persons):
    if p["case_id"] in seen:
        continue
    cluster = [p]
    for j in range(i + 1, len(pending_persons)):
        q = pending_persons[j]
        if q["case_id"] in seen:
            continue
        name_sim = fuzz.token_sort_ratio(
            p["missing_person_name"].lower(),
            q["missing_person_name"].lower()
        )
        same_gender = p["gender"] == q["gender"]
        same_age = p["age_band"] == q["age_band"]
        diff_center = p["reporting_center"] != q["reporting_center"]
        if name_sim > 75 and same_gender and same_age and diff_center:
            cluster.append(q)
            seen.add(q["case_id"])
    if len(cluster) > 1:
        dup_groups.append(cluster)
        seen.add(p["case_id"])

print(f"  Pending/Unresolved with names:  {len(pending_persons)}")
print(f"  Potential cross-center duplicates found: {len(dup_groups)} groups")
if dup_groups:
    print(f"\n  Sample duplicate groups (cross-center matches):")
    for i, group in enumerate(dup_groups[:10]):
        print(f"\n    Group {i+1}:")
        for p in group:
            print(f"      {p['case_id']}  {p['missing_person_name']:<25}  {p['gender']:<8}  {p['age_band']:<6}  Center: {p['reporting_center']}")

# ─── 9. GEOGRAPHIC ANALYSIS ──────────────────────────────────────────
print("\n" + "=" * 70)
print("9. GEOGRAPHIC COVERAGE ANALYSIS")
print("=" * 70)

zone_data = [(z["zone_name"], float(z["centroid_lat"]), float(z["centroid_lng"])) for z in zones]
police_data = [(p["station_name"], float(p["latitude"]), float(p["longitude"])) for p in police]
cctv_locs = [(float(c["latitude"]), float(c["longitude"])) for c in cctv]

print(f"\n  CCTV Coverage by Zone:")
for zname, zlat, zlng in sorted(zone_data, key=lambda x: x[0]):
    nearby_cctv = sum(1 for clat, clng in cctv_locs if haversine_km(zlat, zlng, clat, clng) < 1.0)
    bar = "█" * (nearby_cctv // 2)
    print(f"    {zname:<25} {nearby_cctv:>3} cameras  {bar}")

# Chokepoint analysis
print(f"\n  Chokepoint/Parking Categories:")
choke_cats = Counter(c["category"] for c in chokepoints)
for cat, count in choke_cats.most_common():
    print(f"    {cat:<35} {count:>3}")

# Hotspot analysis — where people go missing most
print(f"\n  Top Missing-Person Hotspots:")
location_counts = Counter(p["last_seen_location"] for p in persons if p["last_seen_location"].strip())
for loc, count in location_counts.most_common(15):
    active = sum(1 for p in persons if p["last_seen_location"] == loc and p["status"] in ("Pending", "Unresolved"))
    print(f"    {loc:<40} {count:>4} total  ({active} still active)")

# Police coverage analysis
print(f"\n  Nearest Police Station to Each Hotspot:")
for loc, count in location_counts.most_common(10):
    for zname, zlat, zlng in zone_data:
        if fuzz.partial_ratio(loc.lower(), zname.lower()) > 50:
            nearest_station = min(police_data, key=lambda s: haversine_km(zlat, zlng, s[1], s[2]))
            dist = haversine_km(zlat, zlng, nearest_station[1], nearest_station[2])
            print(f"    {loc:<40} → {nearest_station[0]} ({dist:.1f} km)")
            break

# ─── 10. LANGUAGE/STATE ANALYSIS ─────────────────────────────────────
print("\n" + "=" * 70)
print("10. LANGUAGE & STATE DISTRIBUTION")
print("=" * 70)

lang_counts = Counter(p["language"] for p in persons if p["language"].strip())
state_counts = Counter(p["state"] for p in persons if p["state"].strip())

print(f"\n  Top Languages:")
for lang, count in lang_counts.most_common(15):
    pct = count / total * 100
    print(f"    {lang:<20} {count:>5}  ({pct:.1f}%)")

print(f"\n  Top States of Origin:")
for state, count in state_counts.most_common(15):
    pct = count / total * 100
    print(f"    {state:<25} {count:>5}  ({pct:.1f}%)")

# ─── 11. SYSTEM PERFORMANCE SUMMARY ──────────────────────────────────
print("\n" + "=" * 70)
print("11. DRISHTI SYSTEM — PERFORMANCE SUMMARY")
print("=" * 70)

print(f"""
  ┌─────────────────────────────────────────────────────────────┐
  │  DRISHTI KUMBH FINDER — KEY METRICS                        │
  ├─────────────────────────────────────────────────────────────┤
  │  Total Cases Processed:        {total:>6,}                       │
  │  Reunification Rate:           {reunited/total*100:>6.1f}%                      │
  │  Average Resolution Time:      {avg_hours:>6.1f} hours                  │
  │  Median Resolution Time:       {median_hours:>6.1f} hours                  │
  │  Cross-Center Duplicates:      {len(dup_groups):>6}                       │
  │  CCTV Cameras Deployed:        {len(cctv):>6,}                       │
  │  Zones Covered:                {len(zones):>6}                       │
  │  Police Stations:              {len(police):>6}                       │
  │  Chokepoints Monitored:        {len(chokepoints):>6}                       │
  │  Reporting Centers:            {len(center_counts):>6}                       │
  │  Most Vulnerable: {most_vulnerable[0]:<12}  {most_vulnerable[1]:>6} cases ({most_vulnerable[1]/total*100:.1f}%)   │
  │  Peak Day Load:                {peak_count:>6} cases                   │
  │  Data Completeness (name):     {(total-no_name)/total*100:>6.1f}%                      │
  │  Data Completeness (mobile):   {(total-no_mobile)/total*100:>6.1f}%                      │
  └─────────────────────────────────────────────────────────────┘
""")

# ─── SAVE JSON RESULTS ───────────────────────────────────────────────

results_json = {
    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "dataset_summary": {
        "total_missing_persons": total,
        "total_cctv_cameras": len(cctv),
        "total_zones": len(zones),
        "total_police_stations": len(police),
        "total_chokepoints": len(chokepoints),
        "total_reporting_centers": len(center_counts),
    },
    "status_breakdown": dict(status_counts),
    "reunification_rate_pct": round(reunited / total * 100, 1),
    "resolution_time": {
        "avg_hours": round(avg_hours, 1),
        "median_hours": round(median_hours, 1),
        "min_hours": round(min_hours, 1),
        "max_hours": round(max_hours, 1),
        "within_1h_pct": round(under_1h / len(resolution_hours) * 100, 1),
        "within_6h_pct": round(under_6h / len(resolution_hours) * 100, 1),
        "within_24h_pct": round(under_24h / len(resolution_hours) * 100, 1),
    },
    "age_distribution": {age: age_counts.get(age, 0) for age in age_order},
    "gender_distribution": dict(gender_counts),
    "data_quality": {
        "missing_name_pct": round(no_name / total * 100, 1),
        "missing_mobile_pct": round(no_mobile / total * 100, 1),
        "missing_description_pct": round(no_desc / total * 100, 1),
        "duplicate_reports_pct": round(duplicates / total * 100, 1),
    },
    "top_reporting_centers": [
        {
            "center": center,
            "cases": count,
            "reunited": center_reunited.get(center, 0),
            "reunification_rate_pct": round(center_reunited.get(center, 0) / count * 100, 1) if count > 0 else 0,
            "avg_resolution_hours": round(sum(center_resolution[center]) / len(center_resolution[center]), 1) if center_resolution[center] else None,
        }
        for center, count in center_counts.most_common()
    ],
    "temporal_patterns": {
        "date_range": f"{sorted_dates[0][0]} to {sorted_dates[-1][0]}",
        "total_days": len(date_counts),
        "avg_daily_cases": round(avg_daily, 1),
        "peak_day": peak_date,
        "peak_day_cases": peak_count,
        "peak_to_avg_ratio": round(peak_count / avg_daily, 1),
        "daily_cases": dict(sorted_dates),
        "hourly_distribution": {f"{h:02d}:00": hour_counts[h] for h in sorted(hour_counts.keys())},
    },
    "top_languages": {lang: count for lang, count in lang_counts.most_common(15)},
    "top_states": {state: count for state, count in state_counts.most_common(15)},
    "hotspots": [
        {
            "location": loc,
            "total_cases": count,
            "active_cases": sum(1 for p in persons if p["last_seen_location"] == loc and p["status"] in ("Pending", "Unresolved")),
        }
        for loc, count in location_counts.most_common(20)
    ],
    "cross_center_duplicate_groups": len(dup_groups),
    "duplicate_group_details": [
        [{"case_id": p["case_id"], "name": p["missing_person_name"], "center": p["reporting_center"],
          "gender": p["gender"], "age_band": p["age_band"]} for p in group]
        for group in dup_groups
    ],
    "cctv_coverage_by_zone": {
        zname: sum(1 for clat, clng in cctv_locs if haversine_km(zlat, zlng, clat, clng) < 1.0)
        for zname, zlat, zlng in zone_data
    },
    "chokepoint_categories": dict(choke_cats),
}

results_path = os.path.join(RESULTS_DIR, "final_results.json")
with open(results_path, "w") as f:
    json.dump(results_json, f, indent=2, ensure_ascii=False)
print(f"Results saved to: {results_path}")

# Also save a text report
report_path = os.path.join(RESULTS_DIR, "final_report.txt")
import io, sys
# We already printed everything above, let's save the summary
with open(report_path, "w") as f:
    f.write("DRISHTI KUMBH FINDER — FINAL ANALYSIS REPORT\n")
    f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("=" * 70 + "\n\n")
    f.write(f"Total Missing Persons Records: {total:,}\n")
    f.write(f"Reunification Rate: {reunited/total*100:.1f}%\n")
    f.write(f"Average Resolution Time: {avg_hours:.1f} hours\n")
    f.write(f"Median Resolution Time: {median_hours:.1f} hours\n")
    f.write(f"Cross-Center Duplicate Groups Found: {len(dup_groups)}\n")
    f.write(f"CCTV Cameras: {len(cctv):,}\n")
    f.write(f"Zones: {len(zones)}\n")
    f.write(f"Police Stations: {len(police)}\n")
    f.write(f"Chokepoints: {len(chokepoints)}\n")
    f.write(f"Reporting Centers: {len(center_counts)}\n\n")
    f.write("STATUS BREAKDOWN:\n")
    for status, count in status_counts.most_common():
        f.write(f"  {status}: {count} ({count/total*100:.1f}%)\n")
    f.write(f"\nAGE DISTRIBUTION:\n")
    for age in age_order:
        f.write(f"  {age}: {age_counts.get(age, 0)} ({age_counts.get(age, 0)/total*100:.1f}%)\n")
    f.write(f"\nGENDER DISTRIBUTION:\n")
    for gender, count in gender_counts.most_common():
        f.write(f"  {gender}: {count} ({count/total*100:.1f}%)\n")
    f.write(f"\nDATA QUALITY:\n")
    f.write(f"  Missing name: {no_name} ({no_name/total*100:.1f}%)\n")
    f.write(f"  Missing mobile: {no_mobile} ({no_mobile/total*100:.1f}%)\n")
    f.write(f"  Duplicates: {duplicates} ({duplicates/total*100:.1f}%)\n")
    f.write(f"\nTOP 15 HOTSPOTS:\n")
    for loc, count in location_counts.most_common(15):
        active = sum(1 for p in persons if p["last_seen_location"] == loc and p["status"] in ("Pending", "Unresolved"))
        f.write(f"  {loc}: {count} total ({active} active)\n")
    f.write(f"\nTOP REPORTING CENTERS:\n")
    for center, count in center_counts.most_common():
        r = center_reunited.get(center, 0)
        rate = r / count * 100 if count > 0 else 0
        f.write(f"  {center}: {count} cases, {r} reunited ({rate:.1f}%)\n")

print(f"Report saved to: {report_path}")
print("\nDone. All results saved to ./results/")
