document.addEventListener("DOMContentLoaded", () => {
  if (typeof L === "undefined") return;

  const street = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  });
  const satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19, attribution: "Tiles &copy; Esri"
  });
  const labels = L.tileLayer("https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png", {
    maxZoom: 19, attribution: '&copy; <a href="https://carto.com/attributions">CARTO</a>'
  });
  function addStyleControl(map, select) {
    if (!map || !select) return;
    function apply() {
      [street, satellite, labels].forEach(layer => { if (map.hasLayer(layer)) map.removeLayer(layer); });
      if (select.value === "satellite") satellite.addTo(map);
      else if (select.value === "hybrid") { satellite.addTo(map); labels.addTo(map); }
      else street.addTo(map);
    }
    apply(); select.addEventListener("change", apply);
  }
  async function searchPlace(query, map, markerLayer, onChoose) {
    if (!query.trim()) return;
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&q=${encodeURIComponent(query)}`, {
        headers: {"Accept":"application/json"}
      });
      if (!response.ok) throw new Error("Search unavailable");
      const results = await response.json();
      if (!results.length) { alert("No matching place found. Try a nearby landmark or street name."); return; }
      if (results.length === 1) {
        const item = results[0], lat = Number(item.lat), lon = Number(item.lon);
        map.setView([lat, lon], 17); onChoose(lat, lon, item.display_name);
      } else {
        const group = L.featureGroup();
        results.forEach(item => {
          const m = L.marker([Number(item.lat), Number(item.lon)]).bindPopup(
            `<strong>${escapeHtml(item.name || item.display_name.split(",")[0])}</strong><br><small>${escapeHtml(item.display_name)}</small>`
          ).addTo(group);
          m.on("click", () => onChoose(Number(item.lat), Number(item.lon), item.display_name));
        });
        group.addTo(map); map.fitBounds(group.getBounds().pad(.18));
      }
    } catch (e) { alert("Place search could not connect. Check your internet connection and try again."); }
  }
  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }
  function makeIcon(color, symbol="●") {
    return L.divIcon({className:"civic-marker-wrap", html:`<div class="civic-marker ${color}">${symbol}</div>`, iconSize:[30,38], iconAnchor:[15,34], popupAnchor:[0,-31]});
  }

  // Citizen complaint location picker
  const mapElement = document.getElementById("issue-map");
  if (mapElement) {
    const map = L.map(mapElement, {zoomControl:true, scrollWheelZoom:true}).setView([28.6139,77.2090], 12);
    addStyleControl(map, document.getElementById("map-style"));
    const message = document.getElementById("location-message");
    const address = document.getElementById("address");
    const latInput = document.getElementById("latitude");
    const lonInput = document.getElementById("longitude");
    const coords = document.getElementById("map-coordinates");
    let marker = null, reverseTimer = null;
    async function setLocation(lat, lon, zoom=17, suppliedAddress="") {
      latInput.value = lat.toFixed(7); lonInput.value = lon.toFixed(7);
      coords.textContent = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
      map.setView([lat,lon], zoom);
      if (!marker) marker = L.marker([lat,lon], {draggable:true, icon:makeIcon("selected","✓")}).addTo(map);
      else marker.setLatLng([lat,lon]);
      marker.off("dragend").on("dragend", e => {
        const p=e.target.getLatLng(); setLocation(p.lat,p.lng,map.getZoom());
      });
      message.textContent = "Pinned location selected. Getting street address…";
      if (suppliedAddress) { address.value=suppliedAddress; message.textContent="Search result selected. You can edit the address if needed."; return; }
      clearTimeout(reverseTimer);
      reverseTimer=setTimeout(async()=>{
        try {
          const r=await fetch(`/api/reverse-geocode?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
          const d=await r.json();
          if(d.address){address.value=d.address;message.textContent="Address found from OpenStreetMap. Verify the street and landmark before submitting.";}
          else message.textContent="Pin saved. Please enter the street name or nearby landmark manually.";
        } catch(_){message.textContent="Pin saved. Please enter the street name or nearby landmark manually.";}
      },250);
    }
    map.on("click", e=>setLocation(e.latlng.lat,e.latlng.lng));
    const locate=document.getElementById("locate-btn");
    locate?.addEventListener("click",()=>{
      if(!navigator.geolocation){message.textContent="GPS is not supported by this browser.";return;}
      locate.disabled=true; message.textContent="Finding your device location…";
      navigator.geolocation.getCurrentPosition(pos=>{
        setLocation(pos.coords.latitude,pos.coords.longitude,18);
        message.textContent += ` GPS accuracy: about ${Math.round(pos.coords.accuracy)} m.`;
        locate.disabled=false;
      },err=>{
        message.textContent=err.code===1?"Location permission denied. Search or click the map instead.":"Could not get GPS. Search or click the map instead.";
        locate.disabled=false;
      },{enableHighAccuracy:true,timeout:15000,maximumAge:30000});
    });
    const search=document.getElementById("map-search"), searchBtn=document.getElementById("map-search-btn");
    const runSearch=()=>searchPlace(search.value,map,null,(lat,lon,name)=>setLocation(lat,lon,17,name));
    searchBtn?.addEventListener("click",runSearch);
    search?.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();runSearch();}});
    document.getElementById("nearby-btn")?.addEventListener("click",async()=>{
      const status=document.getElementById("nearby-status");
      const center=marker?marker.getLatLng():map.getCenter();
      status.textContent="Searching OpenStreetMap for nearby places…";
      const query=`[out:json][timeout:20];(node(around:700,${center.lat},${center.lng})[shop];node(around:700,${center.lat},${center.lng})[amenity~"restaurant|cafe|hospital|pharmacy|school|college|bank|atm|fuel|police|post_office"];way(around:700,${center.lat},${center.lng})[shop];way(around:700,${center.lat},${center.lng})[amenity~"restaurant|cafe|hospital|pharmacy|school|college|bank|atm|fuel|police|post_office"];);out center 45;`;
      try{
        const r=await fetch("https://overpass-api.de/api/interpreter",{method:"POST",body:query});
        if(!r.ok)throw new Error();
        const d=await r.json(); let count=0;
        d.elements.forEach(item=>{
          const lat=item.lat??item.center?.lat, lon=item.lon??item.center?.lon;
          if(!lat||!lon)return;
          const tags=item.tags||{},name=tags.name||tags.shop||tags.amenity||"Nearby place";
          L.circleMarker([lat,lon],{radius:6,color:"#286fba",fillColor:"#5ba5e8",fillOpacity:.9,weight:2})
            .bindPopup(`<strong>${escapeHtml(name)}</strong><br><small>${escapeHtml(tags.amenity||tags.shop||"Place")}</small>`).addTo(map);
          count++;
        });
        status.textContent=count?`${count} nearby places shown. Coverage depends on OpenStreetMap data.`:"No mapped places found in this area.";
      }catch(_){status.textContent="Nearby places could not be loaded right now. Try again later.";}
    });
    const photo=document.getElementById("issue-photo"), photoMessage=document.getElementById("photo-location-message");
    photo?.addEventListener("change",()=>{if(photo.files.length)photoMessage.textContent="Photo selected. The server will check for embedded GPS metadata when submitted.";});
    setTimeout(()=>map.invalidateSize(),300);
  }

  // Admin overview map: all complaints with coordinates, not just filtered rows
  const adminElement=document.getElementById("admin-issue-map");
  if(adminElement){
    const map=L.map(adminElement).setView([28.6139,77.2090],11);
    addStyleControl(map,document.getElementById("admin-map-style"));
    const dataNode=document.getElementById("complaint-map-data");
    let rows=[];try{rows=JSON.parse(dataNode?.textContent||"[]");}catch(_){}
    const bounds=[];
    rows.forEach(c=>{
      const lat=Number(c.latitude),lon=Number(c.longitude);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;
      const cat=String(c.category||"").toLowerCase();
      let color=cat.includes("garbage")||cat.includes("waste")?"green":cat.includes("water")?"blue":cat.includes("light")?"orange":"red";
      const resolved=c.status==="Resolved";
      const marker=L.marker([lat,lon],{icon:makeIcon(resolved?"resolved":color,resolved?"✓":"●")}).addTo(map);
      marker.bindPopup(`<div class="map-popup"><strong>${escapeHtml(c.title)}</strong><span>${escapeHtml(c.ticket_id)}</span><p>${escapeHtml(c.address)}</p><small>${escapeHtml(c.category)} · ${escapeHtml(c.status)}</small><br><a href="/complaint/${Number(c.id)}">Open complaint details →</a></div>`);
      bounds.push([lat,lon]);
    });
    if(bounds.length)map.fitBounds(bounds,{padding:[35,35],maxZoom:15});
    else L.popup().setLatLng(map.getCenter()).setContent("No complaints with GPS coordinates yet.").openOn(map);
    const search=document.getElementById("admin-map-search"),btn=document.getElementById("admin-map-search-btn");
    const run=()=>searchPlace(search.value,map,null,()=>{});
    btn?.addEventListener("click",run);search?.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();run();}});
    setTimeout(()=>map.invalidateSize(),300);
  }

  // Complaint detail location map
  const detailMap=document.getElementById("detail-issue-map");
  if(detailMap){
    const lat=Number(detailMap.dataset.lat),lon=Number(detailMap.dataset.lon);
    if(Number.isFinite(lat)&&Number.isFinite(lon)){
      const map=L.map(detailMap).setView([lat,lon],17);street.addTo(map);
      L.marker([lat,lon],{icon:makeIcon("selected","✓")}).addTo(map).bindPopup("Reported complaint location").openPopup();
      setTimeout(()=>map.invalidateSize(),250);
    }
  }
});
