filter_html = """
<div id="filter-panel">
  <h3>🚲 Filtrer les stations</h3>
  <label>
    <input type="radio" name="filter" value="none" checked onchange="applyFilter(this.value)">
    Toutes les stations
    <span class="count-badge" id="count-none">-</span>
  </label>
  <label>
    <input type="radio" name="filter" value="electrical" onchange="applyFilter(this.value)">
    ⚡ Vélos électriques
    <span class="count-badge" id="count-electrical">-</span>
  </label>
  <label>
    <input type="radio" name="filter" value="mechanical" onchange="applyFilter(this.value)">
    🔧 Vélos mécaniques
    <span class="count-badge" id="count-mechanical">-</span>
  </label>
  <label>
    <input type="radio" name="filter" value="stands" onchange="applyFilter(this.value)">
    🅿️ Places libres
    <span class="count-badge" id="count-stands">-</span>
  </label>
  <hr>
  <div id="legend">
    <div><span class="dot" style="background:#4daf4a"></span> 5+ vélos dispo</div>
    <div><span class="dot" style="background:#ff7f00"></span> 1–4 vélos dispo</div>
    <div><span class="dot" style="background:#e41a1c"></span> Aucun vélo</div>
  </div>
</div>

<script>
  let _markersCache = null;

  function getMap() {
    return Object.values(window).find(
      v => v && typeof v.eachLayer === "function" && v._layers
    );
  }

  function buildCache() {
    const mapObj = getMap();
    if (!mapObj) return false;
    if (typeof STATIONS_DATA === "undefined") return false;

    const markers = [];
    let i = 0;
    mapObj.eachLayer(layer => {
      if (!(layer instanceof L.Marker)) return;
      const d = STATIONS_DATA[i];
      if (!d) return;
      markers.push({
        layer,
        electrical : d.e || 0,
        mechanical : d.m || 0,
        stands     : d.s || 0,
        bikes      : d.b || 0,
      });
      i++;
    });

    if (markers.length === 0) return false;
    _markersCache = markers;
    console.log("Cache built:", markers.length, "markers");
    return true;
  }

  function updateCounts() {
    const m = _markersCache;
    document.getElementById("count-none").textContent       = m.length;
    document.getElementById("count-electrical").textContent = m.filter(x => x.electrical > 0).length;
    document.getElementById("count-mechanical").textContent = m.filter(x => x.mechanical  > 0).length;
    document.getElementById("count-stands").textContent     = m.filter(x => x.stands      > 0).length;
  }

  function applyFilter(value) {
    if (!_markersCache) return;
    _markersCache.forEach(({ layer, electrical, mechanical, stands }) => {
      let visible = true;
      if      (value === "electrical") visible = electrical > 0;
      else if (value === "mechanical") visible = mechanical > 0;
      else if (value === "stands")     visible = stands     > 0;

      const el = layer.getElement();
      if (el) {
        el.style.visibility    = visible ? "visible" : "hidden";
        el.style.pointerEvents = visible ? "auto"    : "none";
      }
    });
  }

  function waitForMarkers() {
    if (buildCache()) {
      updateCounts();
    } else {
      setTimeout(waitForMarkers, 200);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    setTimeout(waitForMarkers, 100);
  });
</script>
"""