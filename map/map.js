/* map/ map.js */
/* =====================================================================
   GCS Web Map  –  OpenLayers 9.1
   • Dinamik-Zoom: polyline + drone ikonu kadraja sığar
   • Kullanıcı etkileşimi → auto-follow anında kapanır
   • goToFocus_pushButton  → auto-follow yeniden açılır (recenterAndFollow)
   • Demo uçuş: HOME etrafında canlı daire
 ===================================================================== */

/* ---------- Sabitler & yardımcı ---------- */
const HOME = { lon: 35.352882053899194, lat: 37.062638526893295 };
const ll   = (lo, la) => ol.proj.fromLonLat([lo, la]);

/* ---------- Küresel objeler ---------- */
let map, view, vectorSrc, droneF, pathF;
let autoFollow = false;
// DEĞİŞİKLİK 1: "İlk paket" durumunu yönetmek için yeni bir bayrak
let isFirstPacket = true;

/* ---------- WebChannel & kurulum ---------- */
window.onload = () => {
  new QWebChannel(qt.webChannelTransport, ch => {
    window.backend = ch.objects.backend;
    initMap();
    backend.onMapReady();
    // Demo'yu otomatik başlat
    startDemoFlight();
  });
};

function initMap() {
  vectorSrc = new ol.source.Vector();

  /* Drone ikonu */
  droneF = new ol.Feature(new ol.geom.Point(ll(HOME.lon, HOME.lat)));
  droneF.setStyle(new ol.style.Style({
    image: new ol.style.Icon({
      src   : '../assets/drone.png', // Göreceli yol varsayımı
      anchor: [0.5, 0.5],
      scale : 0.08,
      rotateWithView: true
    })
  }));

  /* Polyline */
  pathF = new ol.Feature(new ol.geom.LineString([]));
  pathF.setStyle(new ol.style.Style({
    stroke: new ol.style.Stroke({ color:'#1E90FF', width:3 })
  }));

  vectorSrc.addFeatures([droneF, pathF]);

  view = new ol.View({ center: ll(HOME.lon, HOME.lat), zoom: 18 });

  map = new ol.Map({
    target:'map',
    layers:[
      new ol.layer.Tile({ source:new ol.source.OSM() }),
      new ol.layer.Vector({ source:vectorSrc })
    ],
    view:view
  });

  /* DEĞİŞİKLİK 2: Olay dinleyiciyi daha akıllı hale getiriyoruz.
     Programatik hareketlerin (fit, setCenter) `movestart` olayını
     tetikleyip döngüye girmesini engellemek için. */
  map.on('pointerdown', () => {
    if (autoFollow) {
        disableAutoFollow();
    }
  });
}

/* =====================================================================
   Telemetri  (Python → updateDrone({lon,lat,yaw}))
 ===================================================================== */
function updateDrone(p) {
  const coord = ll(p.lon, p.lat);

  /* Drone pozisyonu & yönü */
  droneF.getGeometry().setCoordinates(coord);
  droneF.getStyle().getImage().setRotation((p.yaw||0)*Math.PI/180);

  /* Polyline noktası */
  pathF.getGeometry().appendCoordinate(coord);

  // DEĞİŞİKLİK 3: "İlk paket" mantığını düzeltiyoruz.
  // Bu blok sadece bir kere çalışacak.
  if (isFirstPacket) {
    enableAutoFollow(true); // Auto-follow'u başlat
    isFirstPacket = false;  // Ve bu bayrağı kalıcı olarak kapat
  }

  /* Eğer auto-follow açık ise fit/center işlemleri */
  if (autoFollow) {
    dynamicFit(coord);
  }
}

function dynamicFit(coord) {
  const ext = pathF.getGeometry().getExtent().slice();
  ol.extent.extend(ext, droneF.getGeometry().getExtent());

  const viewExt = view.calculateExtent(map.getSize());
  const polyInView = ol.extent.containsExtent(viewExt, ext);

  if (!polyInView) {
    view.fit(ext, { padding:[80,80,80,80], maxZoom:18, duration:250 });
  } else {
    if (!ol.extent.containsCoordinate(viewExt, coord)) {
      view.animate({ center: coord, duration: 250 });
    }
  }
}

/* =====================================================================
   Auto-follow kontrol
 ===================================================================== */
function enableAutoFollow(skipAnim) {
  if (autoFollow) return; // Zaten açıksa bir şey yapma
  autoFollow = true;
  backend.onDynamicZoomChanged?.(true);

  const ext = pathF.getGeometry().getExtent().slice();
  ol.extent.extend(ext, droneF.getGeometry().getExtent());
  // Extent'in geçerli olduğundan emin ol (polyline boş değilse)
  if (ext[0] !== Infinity) {
      view.fit(ext, { padding:[80,80,80,80], maxZoom:18, duration:skipAnim?0:250 });
  }
}

function disableAutoFollow() {
  if (!autoFollow) return; // Zaten kapalıysa bir şey yapma
  autoFollow = false;
  backend.onDynamicZoomChanged?.(false);
}

/* Python’daki goToFocus_pushButton bu fonksiyonu çağırır */
function recenterAndFollow() { enableAutoFollow(false); }


/* =====================================================================
   Marker & Polyline yardımcıları (butonlar için)
 ===================================================================== */
function addMarker(lon, lat, id) {
  const m = new ol.Feature(new ol.geom.Point(ll(lon, lat)));
  m.setId(id);
  m.setStyle(new ol.style.Style({
    image:new ol.style.Icon({
      src:'../assets/normal_marker.png',
      anchor:[0.5,1], scale:0.10 })
  }));
  vectorSrc.addFeature(m);
}

function clearMarkers() {
  vectorSrc.getFeatures().forEach(f=>{
    if (f !== droneF && f !== pathF) vectorSrc.removeFeature(f);
  });
}

function clearPolyline() {
  pathF.setGeometry(new ol.geom.LineString([]));
  if (autoFollow) disableAutoFollow(); // yol silindi → kapat
}

/* =====================================================================
   DEMO uçuş – 90 m yarıçaplı daire (5 Hz)
 ===================================================================== */
let demoTimer = null;
function startDemoFlight() {
  if (demoTimer) return;
  const R = 90, N = 120;
  const dl = R / 111320;
  const dln= R / (111320*Math.cos(HOME.lat*Math.PI/180));
  const pts=[];
  for (let i=0;i<=N;i++) {
    const t = 2*Math.PI*i/N;
    pts.push({
      lon: HOME.lon + dln*Math.cos(t),
      lat: HOME.lat + dl *Math.sin(t),
      yaw: (t*180/Math.PI+90)%360
    });
  }
  isFirstPacket = true; // Demo başladığında ilk paket bayrağını sıfırla
  clearPolyline();
  let k = 0;
  demoTimer = setInterval(()=>{
    if (k >= pts.length) {
      clearInterval(demoTimer); demoTimer=null;
      backend.onDemoFinished?.(); return;
    }
    updateDrone(pts[k++]);
  }, 200);      // 5 Hz
}