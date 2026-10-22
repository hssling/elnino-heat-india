"""Build pipeline/reference/district_to_imd_subdivision.csv (one row per GADM district, 666 rows).

Sources:
- IMD Hydromet Division "District rainfall distribution" (DAY 14-10-2026), which lists every district under
  its meteorological subdivision: data/external/imd_subdivision/IMD_district_rainfall_distribution_20261014.pdf
  (https://mausam.imd.gov.in/Rainfall/DISTRICT_RAINFALL_DISTRIBUTION_COUNTRY_INDIA_cd.pdf, MANIFEST).
- Subdivision names of the IMD sub-divisional series on data.gov.in (Sub_Division_IMD_2017.csv).

Rule: a district in a state that lies wholly in one subdivision takes that subdivision (basis "state").
Otherwise the GADM district name is matched to IMD's current district list within the state's candidate
subdivisions (basis "name"), or through ALIASES for renamed / differently spelled districts (basis "alias").
GADM 4.1 districts are the 2011-era units; every one lies wholly inside a single subdivision under IMD's
current list (later splits stay within one subdivision), noted per row where relevant.

Run from the repository root: python -m tools.build_subdivision_map  (needs pdfplumber)
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data/external/imd_subdivision/IMD_district_rainfall_distribution_20261014.pdf"
OUT = ROOT / "pipeline/reference/district_to_imd_subdivision.csv"

# IMD current subdivision header (PDF) -> subdivision name in the data.gov.in series (1901-2017).
SUBDIVISIONS = {
    "ANDAMAN & NICOBAR ISLANDS": "Andaman & Nicobar Islands", "ARUNACHAL PRADESH": "Arunachal Pradesh",
    "ASSAM & MEGHALAYA": "Assam & Meghalaya", "NMMT": "Naga Mani Mizo Tripura",
    "SHWB & SIKKIM": "Sub Himalayan West Bengal & Sikkim", "GANGETIC WEST BENGAL": "Gangetic West Bengal",
    "ODISHA": "Orissa", "JHARKHAND": "Jharkhand", "BIHAR": "Bihar", "WEST UTTAR PRADESH": "West Uttar Pradesh",
    "EAST UTTAR PRADESH": "East Uttar Pradesh", "UTTARAKHAND": "Uttarakhand",
    "DELHI AND HARYANA AND CHANDIGARH": "Haryana Delhi & Chandigarh", "PUNJAB": "Punjab",
    "HIMACHAL PRADESH": "Himachal Pradesh", "JAMMU & KASHMIR AND LADAKH": "Jammu & Kashmir",
    "EAST RAJASTHAN": "East Rajasthan", "WEST RAJASTHAN": "West Rajasthan",
    "WEST MADHYA PRADESH": "West Madhya Pradesh", "EAST MADHYA PRADESH": "East Madhya Pradesh",
    "GUJARAT REGION": "Gujarat Region", "SAURASHTRA & KUTCH": "Saurashtra & Kutch", "KONKAN & GOA": "Konkan & Goa",
    "MADHYA MAHARASHTRA": "Madhya Maharashtra", "MARATHWADA": "Matathwada", "VIDARBHA": "Vidarbha",
    "CHHATTISGARH": "Chhattisgarh", "COASTAL ANDHRA PRADESH & YANAM": "Coastal Andhra Pradesh",
    "RAYALASEEMA": "Rayalseema", "TELANGANA": "Telangana", "TAMILNADU & PUDUCHERRY & KARAIKAL": "Tamil Nadu",
    "NORTHERN INTERIOR KARNATAKA": "North Interior Karnataka",
    "SOUTHERN INTERIOR KARNATAKA": "South Interior Karnataka", "COASTAL KARNATAKA": "Coastal Karnataka",
    "KERALA & MAHE": "Kerala", "LAKSHADWEEP": "Lakshadweep",
}
STATE_HEADERS = {"ASSAM", "MEGHALAYA", "MIZORAM", "MANIPUR", "TRIPURA", "NAGALAND", "WEST BENGAL", "SIKKIM",
                 "UTTAR PRADESH", "HARYANA", "DELHI (UT)", "CHANDIGARH (UT)", "JAMMU & KASHMIR (UT)", "LADAKH (UT)",
                 "RAJASTHAN", "MADHYA PRADESH", "GUJARAT", "DADRA & NAGAR HAVELI AND DAMAN & DIU (UT)",
                 "MAHARASHTRA", "GOA", "ANDHRA PRADESH", "PUDUCHERRY (UT)", "TAMILNADU", "KARNATAKA", "KERALA"}
# GADM state -> IMD subdivision(s) (current PDF headers) containing its districts.
STATE_SUBS = {
    "Andaman and Nicobar": ["ANDAMAN & NICOBAR ISLANDS"], "Arunachal Pradesh": ["ARUNACHAL PRADESH"],
    "Assam": ["ASSAM & MEGHALAYA"], "Meghalaya": ["ASSAM & MEGHALAYA"], "Nagaland": ["NMMT"], "Manipur": ["NMMT"],
    "Mizoram": ["NMMT"], "Tripura": ["NMMT"], "Sikkim": ["SHWB & SIKKIM"],
    "West Bengal": ["SHWB & SIKKIM", "GANGETIC WEST BENGAL"], "Odisha": ["ODISHA"], "Jharkhand": ["JHARKHAND"],
    "Bihar": ["BIHAR"], "Uttar Pradesh": ["WEST UTTAR PRADESH", "EAST UTTAR PRADESH"], "Uttarakhand": ["UTTARAKHAND"],
    "Haryana": ["DELHI AND HARYANA AND CHANDIGARH"], "NCT of Delhi": ["DELHI AND HARYANA AND CHANDIGARH"],
    "Chandigarh": ["DELHI AND HARYANA AND CHANDIGARH"], "Punjab": ["PUNJAB"], "Himachal Pradesh": ["HIMACHAL PRADESH"],
    "Jammu and Kashmir": ["JAMMU & KASHMIR AND LADAKH"], "Rajasthan": ["EAST RAJASTHAN", "WEST RAJASTHAN"],
    "Madhya Pradesh": ["WEST MADHYA PRADESH", "EAST MADHYA PRADESH"],
    "Gujarat": ["GUJARAT REGION", "SAURASHTRA & KUTCH"], "Dadra and Nagar Haveli": ["GUJARAT REGION"],
    "Daman and Diu": ["GUJARAT REGION", "SAURASHTRA & KUTCH"], "Goa": ["KONKAN & GOA"],
    "Maharashtra": ["KONKAN & GOA", "MADHYA MAHARASHTRA", "MARATHWADA", "VIDARBHA"],
    "Chhattisgarh": ["CHHATTISGARH"], "Andhra Pradesh": ["COASTAL ANDHRA PRADESH & YANAM", "RAYALASEEMA"],
    "Telangana": ["TELANGANA"], "Tamil Nadu": ["TAMILNADU & PUDUCHERRY & KARAIKAL"],
    "Puducherry": ["TAMILNADU & PUDUCHERRY & KARAIKAL", "COASTAL ANDHRA PRADESH & YANAM", "KERALA & MAHE"],
    "Karnataka": ["NORTHERN INTERIOR KARNATAKA", "SOUTHERN INTERIOR KARNATAKA", "COASTAL KARNATAKA"],
    "Kerala": ["KERALA & MAHE"], "Lakshadweep": ["LAKSHADWEEP"],
}
# (GADM state, GADM district) -> IMD current district name (renamed or differently spelled).
ALIASES = {
    ("West Bengal", "Koch Bihar"): "COOCH BEHAR", ("West Bengal", "Maldah"): "MALDA",
    ("West Bengal", "Uttar Dinajpur"): "NORTH DINAJPUR", ("West Bengal", "Dakshin Dinajpur"): "SOUTH DINAJPUR",
    ("West Bengal", "Darjiling"): "DARJEELING", ("West Bengal", "North 24 Parganas"): "NORTH",
    ("West Bengal", "South 24 Parganas"): "SOUTH", ("West Bengal", "Pashchim Medinipur"): "WEST MIDNAPORE",
    ("West Bengal", "Purba Medinipur"): "EAST MIDNAPORE", ("West Bengal", "Puruliya"): "PURULIA",
    ("West Bengal", "Barddhaman"): "PURBA BARDHAMAN", ("West Bengal", "Haora"): "HOWRAH",
    ("West Bengal", "Hugli"): "HOOGHLY",
    ("Uttar Pradesh", "Budaun"): "BADAUN", ("Uttar Pradesh", "Bulandshahr"): "BULANDSHAHAR",
    ("Uttar Pradesh", "Faizabad"): "AYODHYA", ("Uttar Pradesh", "Allahabad"): "PRAYAGRAJ",
    ("Uttar Pradesh", "Kanpur Nagar"): "KANPUR CITY", ("Uttar Pradesh", "Lakhimpur Kheri"): "KHERI",
    ("Uttar Pradesh", "Rae Bareli"): "RAE BAREILLY", ("Uttar Pradesh", "Sant Ravi Das Nagar"): "BHADOHI",
    ("Uttar Pradesh", "Shravasti"): "SHRAWASTI", ("Uttar Pradesh", "Kushinagar"): "KUSHI NAGAR",
    ("Rajasthan", "Chittaurgarh"): "CHITTORGARH", ("Rajasthan", "Dhaulpur"): "DHOLPUR",
    ("Rajasthan", "Ganganagar"): "SRI GANGANAGAR", ("Rajasthan", "Jalor"): "JALORE",
    ("Rajasthan", "Jhunjhunun"): "JHUNJHUNU",
    ("Madhya Pradesh", "East Nimar"): "KHANDWA", ("Madhya Pradesh", "Hoshangabad"): "NARMADAPURAM",
    ("Madhya Pradesh", "Narsimhapur"): "NARSINGHPUR", ("Madhya Pradesh", "West Nimar"): "KHARGONE",
    ("Gujarat", "Devbhumi Dwarka"): "DEVBHOOMI DWARKA", ("Gujarat", "Kachchh"): "KUTCH",
    ("Gujarat", "Mahesana"): "MEHSANA", ("Gujarat", "Ahmadabad"): "AHMEDABAD",
    ("Gujarat", "Panch Mahals"): "PANCHMAHAL", ("Gujarat", "The Dangs"): "DANGS",
    ("Gujarat", "Chhota Udaipur"): "CHHOTA UDEPUR",
    ("Dadra and Nagar Haveli", "Dadra and Nagar Haveli"): "DADARA & NAGAR HAVELI",
    ("Maharashtra", "Garhchiroli"): "GADCHIROLI", ("Maharashtra", "Gondiya"): "GONDIA",
    ("Maharashtra", "Ahmadnagar"): "AHMEDNAGAR", ("Maharashtra", "Osmanabad"): "DHARASHIV",
    ("Maharashtra", "Solapur"): "SHOLAPUR", ("Maharashtra", "Yavatmal"): "YEOTMAL",
    ("Maharashtra", "Amravati"): "AMRAOTI", ("Maharashtra", "Bid"): "BEED", ("Maharashtra", "Buldana"): "BULDHANA",
    ("Maharashtra", "Aurangabad"): "CHHATRAPATI SAMBHAJINAGAR", ("Maharashtra", "Raigarh"): "RAIGAD",
    ("Andhra Pradesh", "Visakhapatnam"): "VISHAKHAPATNAM", ("Andhra Pradesh", "Y.S.R."): "YSR DISTRICT",
    ("Andhra Pradesh", "Anantapur"): "ANANTAPURAMU", ("Andhra Pradesh", "Nellore"): "SPSR NELLORE",
    ("Karnataka", "Chikmagalur"): "CHIKKAMAGALURU", ("Karnataka", "Davanagere"): "DAVANGERE",
    ("Karnataka", "Gulbarga"): "KALABURAGI", ("Karnataka", "Bagalkot"): "BAGALKOTE", ("Karnataka", "Mysore"): "MYSURU",
    ("Karnataka", "Shimoga"): "SHIVAMOGGA", ("Karnataka", "Tumkur"): "TUMAKURU",
    ("Karnataka", "Bangalore Rural"): "BENGALURU RURAL", ("Karnataka", "Bangalore"): "BENGALURU URBAN",
    ("Karnataka", "Belgaum"): "BELAGAVI", ("Karnataka", "Bellary"): "BALLARI",
    ("Karnataka", "Chamrajnagar"): "CHAMARAJANAGAR", ("Karnataka", "Chikballapura"): "CHIKABALLAPURA",
    ("Karnataka", "Bijapur"): "VIJAYAPURA",
}
NOTES = {
    ("Uttar Pradesh", "Hamirpur"): "Bundelkhand: IMD lists Hamirpur, Jhansi, Jalaun, Lalitpur, Mahoba in West UP; Banda, Chitrakoot in East UP",
    ("Karnataka", "Bellary"): "Ballari (and Vijayanagara, split 2021) listed under South Interior Karnataka",
    ("Andhra Pradesh", "Chittoor"): "Rayalaseema = Anantapur, Chittoor, Kurnool, YSR Kadapa (pre-2022 units); 2022 Tirupati/Annamayya districts also listed in Rayalaseema",
    ("Andhra Pradesh", "Nellore"): "SPSR Nellore in Coastal AP (parts transferred to Tirupati district in 2022 are not represented in GADM 2011 units)",
    ("Puducherry", "Yanam"): "enclave in Coastal Andhra Pradesh & Yanam", ("Puducherry", "Mahe"): "enclave in Kerala & Mahe",
    ("Puducherry", "Karaikal"): "in Tamil Nadu, Puducherry & Karaikal", ("Puducherry", "Puducherry"): "in Tamil Nadu, Puducherry & Karaikal",
    ("Daman and Diu", "Daman"): "Daman listed under Gujarat Region", ("Daman and Diu", "Diu"): "Diu listed under Saurashtra & Kutch",
    ("Jammu and Kashmir", "Leh (Ladakh)"): "IMD subdivision covers J&K and Ladakh (data.gov.in name: Jammu & Kashmir)",
    ("Jammu and Kashmir", "Kargil"): "IMD subdivision covers J&K and Ladakh (data.gov.in name: Jammu & Kashmir)",
    ("West Bengal", "Maldah"): "Malda listed under Sub-Himalayan West Bengal & Sikkim",
    ("Lakshadweep", "Lakshadweep"): "our IMD-grid value is a Kerala-coast proxy (no valid cell over the islands)",
}


def norm(s: str) -> str:
    s = s.upper().replace("&", "AND")
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[^A-Z]", "", s)


def parse_imd_pdf(pdf=PDF) -> pd.DataFrame:
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        text = "\n".join(p.extract_text() or "" for p in doc.pages)
    sub, rows = None, []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("DAY:", "S.No", "India Met", "Hydromet", "DISTRICT RAINFALL")):
            continue
        if line.startswith("LEGEND"):
            break
        m = re.match(r"^(\d+) (.+?)(?: -?[\d.]+| ND)", line)
        if m:
            rows.append((sub, m.group(2).strip()))
            continue
        name = re.sub(r"( -?[\d.]+%?| ND)+.*$", "", line).strip()
        if name in SUBDIVISIONS:
            sub = name
        elif name not in STATE_HEADERS:
            raise ValueError(f"unparsed IMD line: {line!r}")
    return pd.DataFrame(rows, columns=["imd_subdivision_current", "imd_district"])


def build(districts: pd.DataFrame, imd: pd.DataFrame) -> pd.DataFrame:
    out = []
    for r in districts.itertuples():
        subs = STATE_SUBS[r.state_name]
        key = (r.state_name, r.region_name)
        cand = imd[imd.imd_subdivision_current.isin(subs)]
        hit = cand[cand.imd_district.map(norm) == norm(ALIASES.get(key, r.region_name))]
        if len(hit) == 1:
            sub, imd_name, basis = hit.imd_subdivision_current.item(), hit.imd_district.item(), (
                "alias" if key in ALIASES else "name")
        elif len(subs) == 1:
            sub, imd_name, basis = subs[0], "", "state"
        else:
            raise ValueError(f"no unique IMD district for {key}: {hit.imd_district.tolist()}")
        if len(subs) == 1 and basis != "state":
            basis = "state"
        out.append({"region_id": r.region_id, "district_name": r.region_name, "state_name": r.state_name,
                    "imd_subdivision": SUBDIVISIONS[sub], "imd_subdivision_current": sub,
                    "imd_district": imd_name, "basis": basis, "note": NOTES.get(key, "")})
    return pd.DataFrame(out)


def main():
    d = pd.read_csv(ROOT / "data/derived/climate_district_year.csv",
                    usecols=["region_id", "region_name", "state_name"]).drop_duplicates("region_id")
    m = build(d.sort_values("region_id"), parse_imd_pdf())
    m.to_csv(OUT, index=False)
    print(len(m), "districts;", m.imd_subdivision.nunique(), "subdivisions;", m.basis.value_counts().to_dict())


if __name__ == "__main__":
    main()
