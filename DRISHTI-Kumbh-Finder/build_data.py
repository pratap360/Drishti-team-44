"""
build_data.py — turn the CSV dataset into a single embedded app_data.js
so the DRISHTI app runs fully OFFLINE (no fetch, no server, no network).

Run:  python3 build_data.py
Reads:  data/*.csv
Writes: app_data.js   (window.KMP = {...})
"""
import csv, json, os, re
import xml.etree.ElementTree as ET

BASE = os.path.dirname(__file__)
DATA = os.path.join(BASE, "data")

def rows(name):
    with open(os.path.join(DATA, name), newline="") as f:
        return list(csv.DictReader(f))

def kml_points(filename):
    """Yield {name, lat, lng} for every Placemark that has a <Point> in a KML file.
    KML is just XML; we ignore namespaces with the {*} wildcard so the parser
    works regardless of how Google Earth prefixed the tags."""
    out = []
    root = ET.parse(os.path.join(BASE, filename)).getroot()
    for pm in root.findall(".//{*}Placemark"):
        name = pm.find("{*}name")
        coord = pm.find(".//{*}coordinates")
        if name is None or coord is None or not (coord.text and coord.text.strip()):
            continue
        lng, lat = (float(x) for x in coord.text.strip().split(",")[:2])
        out.append({"name": name.text.strip(), "lat": lat, "lng": lng})
    return out

# A KML placemark is a real camera if its name is a camera code: the zone
# cameras (Z<n>-C<m>) plus the general / mobile / gate / ring-road cameras
# (C-, M-, G-, RRC). Everything else in the file (zone-label markers, ring-road
# segments, ghat names) is NOT a camera and is excluded.
CAM_NAME = re.compile(r"^\s*(Z\d+-C\d+|C-\d+|M-\d+|G-\d+|RRC\s*\d+)", re.I)

def explicit_zone(cam_name):
    """Zone cameras carry their zone in the name (Z7-C3 → Zone Area 7).
    Other camera types have no zone in the name and get one geographically."""
    m = re.match(r"\s*Z(\d+)-C", cam_name or "", re.I)
    return f"Zone Area {int(m.group(1))}" if m else None

def mask_mobile(m):
    """Privacy by design: keep country code + last 2 digits, mask the rest."""
    if not m:
        return ""
    digits = re.sub(r"\D", "", m)
    if len(digits) < 4:
        return "•••"
    return "+91 ••••••" + digits[-2:]

# ---- missing persons (2500) ----
persons = []
for r in rows("Synthetic_Missing_Persons_2500.csv"):
    persons.append({
        "id": r["case_id"],
        "t": r["reported_at"],
        "name": r["missing_person_name"].strip(),
        "g": r["gender"],
        "age": r["age_band"],
        "state": r["state"],
        "dist": r["district"],
        "lang": r["language"],
        "seen": r["last_seen_location"],
        "center": r["reporting_center"],
        "mob": mask_mobile(r["reporter_mobile"]),
        "desc": r["physical_description"].strip(),
        "status": r["status"],
        "rh": r["resolution_hours"],
        "dup": r["is_duplicate_report"].strip().lower() == "true",
        "rem": r["remarks"].strip(),
    })

# ---- zones (32) ----
zones = [{"name": r["zone_name"],
          "lat": float(r["centroid_lat"]), "lng": float(r["centroid_lng"]),
          "pts": int(r["approx_boundary_points"])}
         for r in rows("Zone_Boundaries.csv")]

def nearest_zone(lat, lng):
    """Snap a point to the closest zone centroid."""
    return min(zones, key=lambda z: (z["lat"] - lat) ** 2 + (z["lng"] - lng) ** 2)

# ---- cameras ----
# Prefer the richer CCTV Dataset.kml (~4,079 cameras of several types) over the
# flat 1,280-row CSV. Every camera gets a zone — from its name when it encodes
# one (Z7-C3), else by nearest zone centroid. The zone tag powers the no-photo
# workflow: person last seen in Zone N → the exact camera IDs to pull footage from.
CCTV_KML = "CCTV Dataset.kml"
if os.path.exists(os.path.join(BASE, CCTV_KML)):
    cameras = []
    for p in kml_points(CCTV_KML):
        if not CAM_NAME.match(p["name"]):
            continue                       # skip zone-label markers, segments, ghats
        zone = explicit_zone(p["name"]) or nearest_zone(p["lat"], p["lng"])["name"]
        cameras.append({"id": p["name"], "lng": p["lng"], "lat": p["lat"], "zone": zone})
    cam_source = CCTV_KML
else:
    cameras = [{"id": r["camera_id"], "lng": float(r["longitude"]),
                "lat": float(r["latitude"]),
                "zone": nearest_zone(float(r["latitude"]), float(r["longitude"]))["name"]}
               for r in rows("CCTV_Locations.csv")]
    cam_source = "CCTV_Locations.csv"

# how many cameras sit in each zone (for the no-photo CCTV review packet)
zone_cam_count = {}
for c in cameras:
    zone_cam_count[c["zone"]] = zone_cam_count.get(c["zone"], 0) + 1
for z in zones:
    z["cams"] = zone_cam_count.get(z["name"], 0)

# ---- police (14) ----
police = [{"name": r["station_name"],
           "lng": float(r["longitude"]), "lat": float(r["latitude"])}
          for r in rows("Police_Stations.csv")]

# ---- chokepoints / parking (85) ----
choke = [{"name": r["location_name"], "cat": r["category"],
          "lng": float(r["longitude"]), "lat": float(r["latitude"])}
         for r in rows("Chokepoints_Parking.csv")]

# ---- approximate coordinates for the 20 named last-seen locations ----
# (snap each named location to the nearest chokepoint/zone centroid that
#  matches its name, else to the overall centroid — gives the map a pin)
def centroid(items):
    return (sum(i["lat"] for i in items) / len(items),
            sum(i["lng"] for i in items) / len(items))
clat, clng = centroid(cameras)

seen_locs = sorted({p["seen"] for p in persons if p["seen"]})
seen_coords = {}
ref = choke + [{"name": pp["name"], "lat": pp["lat"], "lng": pp["lng"]} for pp in police]

for i, s in enumerate(seen_locs):
    key = re.sub(r"[^a-z]", "", s.lower())
    base = None
    for r in ref:                      # try to anchor by name (chokepoint / police)
        rk = re.sub(r"[^a-z]", "", r["name"].lower())
        if key[:5] and (key[:5] in rk or rk[:5] in key):
            base = (r["lat"], r["lng"]); break
    if base is None:                   # else spread deterministically across zones
        z = zones[i % len(zones)]
        base = (z["lat"], z["lng"])
    z = nearest_zone(*base)            # final: snap onto a zone centroid (camera-dense)
    seen_coords[s] = {"lat": z["lat"], "lng": z["lng"], "zone": z["name"]}

KMP = {"persons": persons, "cameras": cameras, "zones": zones,
       "police": police, "choke": choke, "seenCoords": seen_coords,
       "bbox": {"latMin": min(c["lat"] for c in cameras),
                "latMax": max(c["lat"] for c in cameras),
                "lngMin": min(c["lng"] for c in cameras),
                "lngMax": max(c["lng"] for c in cameras)}}

out = os.path.join(os.path.dirname(__file__), "app_data.js")
with open(out, "w") as f:
    f.write("// Auto-generated by build_data.py — embedded so the app runs fully offline.\n")
    f.write("window.KMP = ")
    json.dump(KMP, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")

print(f"persons={len(persons)} cameras={len(cameras)} (from {cam_source}) "
      f"zones={len(zones)} police={len(police)} choke={len(choke)} "
      f"seenLocs={len(seen_coords)}")
print(f"wrote {out} ({os.path.getsize(out)//1024} KB)")
