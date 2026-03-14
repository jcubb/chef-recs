import json
from pathlib import Path
from datetime import date

DOCS_DIR = Path(__file__).parent.parent / "docs"
DATA_FILE = Path(__file__).parent.parent / "data" / "restaurants.json"


def build_site() -> None:
    DOCS_DIR.mkdir(exist_ok=True)

    restaurants = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else []
    data_json = json.dumps(restaurants, ensure_ascii=False)
    today = date.today().isoformat()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Chef Recs</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg: #0f0f0f;
      --surface: #1a1a1a;
      --surface2: #242424;
      --border: #2e2e2e;
      --text: #e8e8e8;
      --text-muted: #888;
      --accent: #d4a853;
      --accent-dim: rgba(212,168,83,0.15);
      --radius: 8px;
    }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 15px;
      line-height: 1.5;
    }}

    header {{
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 12px;
      position: sticky;
      top: 0;
      background: var(--bg);
      z-index: 100;
    }}

    header h1 {{
      font-size: 18px;
      font-weight: 600;
      letter-spacing: -0.3px;
      flex: 1;
    }}

    header h1 span {{ color: var(--accent); }}

    #total-count {{
      font-size: 13px;
      color: var(--text-muted);
    }}

    .view-toggle {{
      display: flex;
      gap: 4px;
    }}

    .view-btn {{
      padding: 6px 14px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 13px;
      transition: all 0.15s;
    }}

    .view-btn.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: #000;
      font-weight: 600;
    }}

    .filters {{
      padding: 12px 20px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }}

    .filters input, .filters select {{
      padding: 7px 11px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text);
      font-size: 13px;
      min-width: 140px;
    }}

    .filters input {{ flex: 1; min-width: 160px; }}
    .filters input:focus, .filters select:focus {{
      outline: none;
      border-color: var(--accent);
    }}

    #result-count {{
      font-size: 13px;
      color: var(--text-muted);
      padding: 10px 20px 0;
    }}

    /* ── List view ── */
    #list-view {{
      padding: 12px 20px 40px;
    }}

    .restaurant-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}

    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      transition: border-color 0.15s;
    }}

    .card:hover {{ border-color: var(--accent); }}

    .card-name {{
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 4px;
    }}

    .card-meta {{
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 10px;
    }}

    .card-meta span + span::before {{ content: " · "; }}

    .tag-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin-bottom: 8px;
    }}

    .tag {{
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 20px;
      background: var(--surface2);
      color: var(--text-muted);
      border: 1px solid var(--border);
    }}

    .tag.cuisine {{ background: var(--accent-dim); color: var(--accent); border-color: transparent; }}

    .dishes {{
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 8px;
    }}

    .dishes strong {{ color: var(--text); }}

    .context {{
      font-size: 13px;
      color: var(--text-muted);
      font-style: italic;
      border-left: 2px solid var(--border);
      padding-left: 8px;
    }}

    /* ── Map view ── */
    #map-view {{ display: none; }}
    #map {{ height: calc(100vh - 120px); }}

    /* Leaflet popup overrides */
    .leaflet-popup-content-wrapper {{
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }}
    .leaflet-popup-tip {{ background: var(--surface); }}
    .leaflet-popup-content {{ margin: 12px 14px; font-size: 13px; line-height: 1.5; }}
    .popup-name {{ font-size: 15px; font-weight: 600; margin-bottom: 4px; }}
    .popup-meta {{ color: var(--text-muted); font-size: 12px; margin-bottom: 6px; }}

    /* ── Empty state ── */
    .empty {{
      text-align: center;
      padding: 60px 20px;
      color: var(--text-muted);
    }}
    .empty h2 {{ font-size: 20px; margin-bottom: 8px; color: var(--text); }}

    @media (max-width: 600px) {{
      .restaurant-grid {{ grid-template-columns: 1fr; }}
      header {{ flex-wrap: wrap; }}
      .filters {{ padding: 10px 14px; }}
      #list-view {{ padding: 10px 14px 40px; }}
    }}
  </style>
</head>
<body>

<header>
  <h1><span>&#127869;</span> Chef Recs</h1>
  <span id="total-count"></span>
  <div class="view-toggle">
    <button class="view-btn active" onclick="showView('list')">List</button>
    <button class="view-btn" onclick="showView('map')">Map</button>
  </div>
</header>

<div class="filters">
  <input type="text" id="search" placeholder="Search restaurants..." oninput="applyFilters()" />
  <select id="filter-neighborhood" onchange="applyFilters()">
    <option value="">All neighborhoods</option>
  </select>
  <select id="filter-cuisine" onchange="applyFilters()">
    <option value="">All cuisines</option>
  </select>
  <select id="filter-chef" onchange="applyFilters()">
    <option value="">All chefs</option>
  </select>
  <select id="filter-source" onchange="applyFilters()">
    <option value="">All sources</option>
  </select>
</div>

<div id="result-count"></div>

<div id="list-view">
  <div class="restaurant-grid" id="grid"></div>
</div>

<div id="map-view">
  <div id="map"></div>
</div>

<script>
const ALL_RESTAURANTS = {data_json};

let filtered = [...ALL_RESTAURANTS];
let map = null;
let markers = [];

// ── Bootstrap ──────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {{
  document.getElementById('total-count').textContent =
    ALL_RESTAURANTS.length + ' restaurants';
  populateFilters();
  applyFilters();
}});

// ── Filters ────────────────────────────────────────────────────────────────

function populateFilters() {{
  const neighborhoods = new Set();
  const cuisines = new Set();
  const chefs = new Set();
  const sources = new Set();

  ALL_RESTAURANTS.forEach(r => {{
    if (r.neighborhood) neighborhoods.add(r.neighborhood);
    if (r.cuisine) cuisines.add(r.cuisine);
    r.recommended_by.forEach(rb => chefs.add(rb.chef));
    r.recommended_by.forEach(rb => sources.add(rb.source_name));
  }});

  populateSelect('filter-neighborhood', [...neighborhoods].sort());
  populateSelect('filter-cuisine', [...cuisines].sort());
  populateSelect('filter-chef', [...chefs].sort());
  populateSelect('filter-source', [...sources].sort());
}}

function populateSelect(id, values) {{
  const sel = document.getElementById(id);
  values.forEach(v => {{
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  }});
}}

function applyFilters() {{
  const q = document.getElementById('search').value.toLowerCase();
  const nbhd = document.getElementById('filter-neighborhood').value;
  const cuisine = document.getElementById('filter-cuisine').value;
  const chef = document.getElementById('filter-chef').value;
  const source = document.getElementById('filter-source').value;

  filtered = ALL_RESTAURANTS.filter(r => {{
    if (q && !r.name.toLowerCase().includes(q) &&
        !r.neighborhood.toLowerCase().includes(q) &&
        !r.cuisine.toLowerCase().includes(q)) return false;
    if (nbhd && r.neighborhood !== nbhd) return false;
    if (cuisine && r.cuisine !== cuisine) return false;
    if (chef && !r.recommended_by.some(rb => rb.chef === chef)) return false;
    if (source && !r.recommended_by.some(rb => rb.source_name === source)) return false;
    return true;
  }});

  document.getElementById('result-count').textContent =
    filtered.length === ALL_RESTAURANTS.length
      ? ''
      : `Showing ${{filtered.length}} of ${{ALL_RESTAURANTS.length}}`;

  renderList();
  if (map) renderMapMarkers();
}}

// ── List view ──────────────────────────────────────────────────────────────

function renderList() {{
  const grid = document.getElementById('grid');
  if (filtered.length === 0) {{
    grid.innerHTML = '<div class="empty"><h2>No results</h2><p>Try adjusting your filters.</p></div>';
    return;
  }}

  grid.innerHTML = filtered.map(r => {{
    const chefNames = r.recommended_by.map(rb => rb.chef).join(', ');
    const metaParts = [];
    if (r.neighborhood) metaParts.push(r.neighborhood);
    if (r.city) metaParts.push(r.city);

    const dishesHtml = r.recommended_dishes.length
      ? `<div class="dishes"><strong>Try:</strong> ${{r.recommended_dishes.join(', ')}}</div>`
      : '';

    const contextHtml = r.context.length
      ? `<div class="context">${{r.context[0]}}</div>`
      : '';

    const chefTags = r.recommended_by.map(rb =>
      `<span class="tag" title="${{rb.source_name}}">${{rb.chef}}</span>`
    ).join('');

    const cuisineTag = r.cuisine
      ? `<span class="tag cuisine">${{r.cuisine}}</span>`
      : '';

    return `<div class="card">
      <div class="card-name">${{r.name}}</div>
      <div class="card-meta">${{metaParts.map(p => `<span>${{p}}</span>`).join('')}}</div>
      <div class="tag-row">${{cuisineTag}}${{chefTags}}</div>
      ${{dishesHtml}}
      ${{contextHtml}}
    </div>`;
  }}).join('');
}}

// ── Map view ───────────────────────────────────────────────────────────────

function initMap() {{
  map = L.map('map').setView([40.73, -73.99], 12);
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '&copy; OpenStreetMap &copy; CartoDB',
    subdomains: 'abcd',
    maxZoom: 19
  }}).addTo(map);
  renderMapMarkers();
}}

function renderMapMarkers() {{
  markers.forEach(m => m.remove());
  markers = [];

  const mappable = filtered.filter(r => r.latitude != null);

  mappable.forEach(r => {{
    const chefs = r.recommended_by.map(rb => `<span>${{rb.chef}}</span>`).join(' · ');
    const dishes = r.recommended_dishes.length
      ? `<div style="margin-top:4px;color:#aaa;font-size:12px">Try: ${{r.recommended_dishes.join(', ')}}</div>`
      : '';

    const popup = `<div class="popup-name">${{r.name}}</div>
      <div class="popup-meta">${{[r.neighborhood, r.city].filter(Boolean).join(', ')}}</div>
      <div style="font-size:12px;color:#aaa">${{chefs}}</div>
      ${{dishes}}`;

    const dot = L.circleMarker([r.latitude, r.longitude], {{
      radius: 7,
      fillColor: '#d4a853',
      color: '#0f0f0f',
      weight: 1.5,
      opacity: 1,
      fillOpacity: 0.85
    }}).bindPopup(popup);

    dot.addTo(map);
    markers.push(dot);
  }});
}}

// ── View toggle ────────────────────────────────────────────────────────────

function showView(view) {{
  document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');

  const listEl = document.getElementById('list-view');
  const mapEl = document.getElementById('map-view');

  if (view === 'map') {{
    listEl.style.display = 'none';
    mapEl.style.display = 'block';
    if (!map) initMap();
    else renderMapMarkers();
  }} else {{
    mapEl.style.display = 'none';
    listEl.style.display = 'block';
  }}
}}
</script>

<!-- Last generated: {today} -->
</body>
</html>"""

    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"[site] Built docs/index.html ({len(restaurants)} restaurants)")
