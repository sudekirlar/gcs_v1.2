/* map/ map.js */
/* =====================================================================
   GCS Web Map  –  OpenLayers 9.1
   • Dinamik-Zoom: drone + iz + (takip grubundaki) mobil marker’lar kadraja sığar
   • Kullanıcı etkileşimi → auto-follow anında kapanır
   • goToFocus_pushButton → her durumda (açıksa/kapalıysa) taze fit (recenterAndFollow)
   • Demo uçuş: HOME etrafında canlı daire
 ===================================================================== */

/* ---------- Sabitler & yardımcı ---------- */
const HOME = { lon: 35.352882053899194, lat: 37.062638526893295 };
const ll   = (lo, la) => ol.proj.fromLonLat([lo, la]);

/* ---------- Küresel objeler ---------- */
let map, view, vectorSrc, droneF, pathF;
let autoFollow = false;
// "İlk paket" durumunu yönetmek için bayrak
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
  droneF.set('fitGroup', 'follow');   // dinamik kadraj grubunda

  /* Polyline */
  pathF = new ol.Feature(new ol.geom.LineString([]));
  pathF.setStyle(new ol.style.Style({
    stroke: new ol.style.Stroke({ color:'#1E90FF', width:3 })
  }));
  pathF.set('fitGroup', 'follow');    // dinamik kadraj grubunda

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

  // Kullanıcı haritayı oynatırsa auto-follow’u kapat
  map.on('pointerdown', () => {
    if (autoFollow) {
      disableAutoFollow();
    }
  });
}

/* =====================================================================
   Ortak: follow grubunun tamamını kadraja sığdır
 ===================================================================== */
function fitFollowExtent(skipAnim) {
  const ext = [Infinity, Infinity, -Infinity, -Infinity];
  vectorSrc.getFeatures().forEach(f => {
    if (f.get('fitGroup') === 'follow' && f.getGeometry()) {
      ol.extent.extend(ext, f.getGeometry().getExtent());
    }
  });
  if (ext[0] !== Infinity) {
    view.fit(ext, {
      padding:[80,80,80,80],
      maxZoom:18,
      duration: skipAnim ? 0 : 250
    });
  }
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

  // İlk paket geldiyse auto-follow’u aç ve taze fit yap (animasyonsuz)
  if (isFirstPacket) {
    enableAutoFollow(true);
    isFirstPacket = false;
  }

  /* Auto-follow açıkken dinamik kadraj yönetimi */
  if (autoFollow) {
    dynamicFit(coord);
  }
}

function dynamicFit(coord) {
  // follow grubundaki tüm feature’ları kadraja al
  const ext = [Infinity, Infinity, -Infinity, -Infinity];
  vectorSrc.getFeatures().forEach(f => {
    if (f.get('fitGroup') === 'follow' && f.getGeometry()) {
      ol.extent.extend(ext, f.getGeometry().getExtent());
    }
  });

  const viewExt   = view.calculateExtent(map.getSize());
  const allInView = ol.extent.containsExtent(viewExt, ext);

  if (!allInView) {
    view.fit(ext, { padding:[80,80,80,80], maxZoom:18, duration:250 });
  } else {
    // Hepsi kadrajda ama drone merkezden çıktıysa küçük bir center animasyonu
    if (!ol.extent.containsCoordinate(viewExt, coord)) {
      view.animate({ center: coord, duration: 250 });
    }
  }
}

/* =====================================================================
   Auto-follow kontrol
 ===================================================================== */
function enableAutoFollow(skipAnim) {
  // Açık değilse aç; açıksa da taze bir fit uygula
  if (!autoFollow) {
    autoFollow = true;
    backend.onDynamicZoomChanged?.(true);
  }
  fitFollowExtent(!!skipAnim);
}

function disableAutoFollow() {
  if (!autoFollow) return;
  autoFollow = false;
  backend.onDynamicZoomChanged?.(false);
}

/* Python’daki goToFocus_pushButton bu fonksiyonu çağırır */
function recenterAndFollow() {
  // Focus: auto-follow’u aç ve follow grubunu DERHAL kadraja sığdır
  enableAutoFollow(false);
}

/* =====================================================================
   Marker & Polyline yardımcıları (butonlar için)
 ===================================================================== */
function addMarker(lon, lat, id) {
  const m = new ol.Feature(new ol.geom.Point(ll(lon, lat)));
  m.setId(id);
  m.setStyle(new ol.style.Style({
    image:new ol.style.Icon({
      src:'../assets/normal_marker.png',
      anchor:[0.5,1],
      scale:0.10
    })
  }));
  vectorSrc.addFeature(m);
}

// Mobil bildirim marker’ı (özel ikon + follow grubuna dahil)
function addMobileMarker(lon, lat, id) {
  const f = new ol.Feature(new ol.geom.Point(ll(lon, lat)));
  f.setId(id);
  f.set('fitGroup', 'follow');  // dinamik kadrajın parçası olsun
  f.setStyle(new ol.style.Style({
    image:new ol.style.Icon({
      src:'../assets/mobile_marker.png',
      anchor:[0.5,1],
      scale:0.12
    })
  }));
  vectorSrc.addFeature(f);

  // Auto-follow açıksa follow grubunun tamamına taze fit
  if (autoFollow) {
    fitFollowExtent(false);
  }
}

function clearMarkers() {
  vectorSrc.getFeatures().forEach(f => {
    if (f !== droneF && f !== pathF) {
      vectorSrc.removeFeature(f);
    }
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
  const dl  = R / 111320;
  const dln = R / (111320*Math.cos(HOME.lat*Math.PI/180));
  const pts = [];
  for (let i=0; i<=N; i++) {
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
  demoTimer = setInterval(() => {
    if (k >= pts.length) {
      clearInterval(demoTimer);
      demoTimer = null;
      backend.onDemoFinished?.();
      return;
    }
    updateDrone(pts[k++]);
  }, 200); // 5 Hz
}
