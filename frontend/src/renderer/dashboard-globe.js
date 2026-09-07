"use strict";

// Globo 3D del dashboard. Está aislado de los módulos de automatización y
// conserva el planeta CSS anterior como fallback si WebGL/Three.js no cargan.
const THREE_MODULE_URL = "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js";
const STYLE_ID = "dashboard-globe-three-style";
let activeGlobe = null;

const LOCATIONS = [
  { name: "Quito", lat: -0.18, lon: -78.47, hub: true },
  { name: "Bogotá", lat: 4.71, lon: -74.07 },
  { name: "Ciudad de México", lat: 19.43, lon: -99.13, hub: true },
  { name: "Lima", lat: -12.05, lon: -77.04 },
  { name: "Asunción", lat: -25.27, lon: -57.58 },
  { name: "Nueva York", lat: 40.71, lon: -74.0 },
  { name: "Madrid", lat: 40.42, lon: -3.7, hub: true },
  { name: "Londres", lat: 51.5, lon: -0.12 },
  { name: "Tokio", lat: 35.67, lon: 139.65, hub: true },
  { name: "Singapur", lat: 1.35, lon: 103.81 },
];

const ROUTES = [
  [0, 2, 0.24], [0, 6, 0.34], [1, 5, 0.22],
  [3, 7, 0.31], [6, 8, 0.38], [8, 9, 0.18],
];

function installStylesheet() {
  if (document.getElementById(STYLE_ID)) return;
  const link = document.createElement("link");
  link.id = STYLE_ID;
  link.rel = "stylesheet";
  link.href = new URL("./dashboard-globe.css?v=utel-three-1", import.meta.url).href;
  document.head.appendChild(link);
}

function latLonToVector3(THREE, lat, lon, radius = 1) {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function makeGlowTexture(THREE, size = 96) {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  const center = size / 2;
  const gradient = context.createRadialGradient(center, center, 0, center, center, center);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.16, "rgba(220,255,255,.95)");
  gradient.addColorStop(0.42, "rgba(23,237,245,.48)");
  gradient.addColorStop(1, "rgba(23,237,245,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function createDashboardGlobe(THREE, container) {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100);
  camera.position.set(0, 0.02, 4.05);

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.domElement.setAttribute("aria-hidden", "true");
  container.appendChild(renderer.domElement);

  const stage = new THREE.Group();
  scene.add(stage);
  const globe = new THREE.Group();
  globe.rotation.set(-0.06, -0.58, -0.02);
  stage.add(globe);

  scene.add(new THREE.AmbientLight(0x0b5f70, 0.72));
  const key = new THREE.PointLight(0x17edf5, 4.4, 12, 1.9);
  key.position.set(2.8, 2.2, 4.2);
  scene.add(key);
  const rim = new THREE.PointLight(0x31ffd6, 2.4, 10, 2);
  rim.position.set(-2.4, -2.2, 1.2);
  scene.add(rim);

  const sphereGeometry = new THREE.SphereGeometry(1, 80, 80);
  globe.add(new THREE.Mesh(
    sphereGeometry,
    new THREE.MeshPhongMaterial({
      color: 0x01070d,
      emissive: 0x001017,
      emissiveIntensity: 0.72,
      shininess: 44,
      transparent: true,
      opacity: 0.34,
    }),
  ));

  const gridMaterial = new THREE.LineBasicMaterial({
    color: 0x0fd8e4,
    transparent: true,
    opacity: 0.105,
    depthWrite: false,
  });
  for (let lat = -75; lat <= 75; lat += 15) {
    const latRad = THREE.MathUtils.degToRad(lat);
    const y = 1.006 * Math.sin(latRad);
    const ringRadius = 1.006 * Math.cos(latRad);
    const points = [];
    for (let index = 0; index <= 96; index += 1) {
      const angle = index / 96 * Math.PI * 2;
      points.push(new THREE.Vector3(ringRadius * Math.cos(angle), y, ringRadius * Math.sin(angle)));
    }
    globe.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points), gridMaterial));
  }
  for (let lon = -180; lon < 180; lon += 15) {
    const points = [];
    for (let lat = -90; lat <= 90; lat += 4) points.push(latLonToVector3(THREE, lat, lon, 1.006));
    globe.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), gridMaterial));
  }

  const wire = new THREE.LineSegments(
    new THREE.WireframeGeometry(new THREE.IcosahedronGeometry(1.012, 5)),
    new THREE.LineBasicMaterial({ color: 0x45b9ff, transparent: true, opacity: 0.095, depthWrite: false }),
  );
  globe.add(wire);

  const surfaceCount = 920;
  const surfacePositions = new Float32Array(surfaceCount * 3);
  for (let index = 0; index < surfaceCount; index += 1) {
    const y = 1 - (index / Math.max(surfaceCount - 1, 1)) * 2;
    const radius = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = Math.PI * (3 - Math.sqrt(5)) * index;
    const jitter = 1.016 + Math.sin(index * 2.37) * 0.002;
    surfacePositions[index * 3] = Math.cos(theta) * radius * jitter;
    surfacePositions[index * 3 + 1] = y * jitter;
    surfacePositions[index * 3 + 2] = Math.sin(theta) * radius * jitter;
  }
  const surfaceGeometry = new THREE.BufferGeometry();
  surfaceGeometry.setAttribute("position", new THREE.BufferAttribute(surfacePositions, 3));
  const surfacePoints = new THREE.Points(
    surfaceGeometry,
    new THREE.PointsMaterial({ color: 0x17edf5, size: 0.009, transparent: true, opacity: 0.28, depthWrite: false }),
  );
  globe.add(surfacePoints);

  const atmosphereMaterial = new THREE.ShaderMaterial({
    uniforms: { glowColor: { value: new THREE.Color(0x12e7ef) }, intensity: { value: 0.84 } },
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vWorldPosition;
      void main(){
        vNormal = normalize(normalMatrix * normal);
        vec4 worldPosition = modelMatrix * vec4(position, 1.0);
        vWorldPosition = worldPosition.xyz;
        gl_Position = projectionMatrix * viewMatrix * worldPosition;
      }
    `,
    fragmentShader: `
      uniform vec3 glowColor;
      uniform float intensity;
      varying vec3 vNormal;
      varying vec3 vWorldPosition;
      void main(){
        vec3 viewDirection = normalize(cameraPosition - vWorldPosition);
        float fresnel = pow(1.0 - max(dot(vNormal, viewDirection), 0.0), 3.0);
        gl_FragColor = vec4(glowColor, fresnel * 0.36 * intensity);
      }
    `,
    transparent: true,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  globe.add(new THREE.Mesh(new THREE.SphereGeometry(1.045, 72, 72), atmosphereMaterial));

  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(1.095, 48, 48),
    new THREE.MeshBasicMaterial({ color: 0x45b9ff, transparent: true, opacity: 0.018, side: THREE.BackSide, depthWrite: false }),
  );
  globe.add(halo);

  const glowTexture = makeGlowTexture(THREE);
  const nodes = [];
  const nodeByIndex = new Map();
  const forward = new THREE.Vector3(0, 0, 1);

  LOCATIONS.forEach((location, index) => {
    const group = new THREE.Group();
    const position = latLonToVector3(THREE, location.lat, location.lon, 1.03);
    const normal = position.clone().normalize();
    group.position.copy(position);
    const core = new THREE.Mesh(
      new THREE.SphereGeometry(location.hub ? 0.018 : 0.012, 14, 14),
      new THREE.MeshBasicMaterial({ color: location.hub ? 0xd8ffff : 0x17edf5, blending: THREE.AdditiveBlending, depthWrite: false }),
    );
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowTexture,
      color: location.hub ? 0x31ffd6 : 0x17edf5,
      transparent: true,
      opacity: location.hub ? 0.75 : 0.5,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }));
    const glowScale = location.hub ? 0.17 : 0.105;
    glow.scale.set(glowScale, glowScale, 1);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(location.hub ? 0.032 : 0.024, location.hub ? 0.037 : 0.028, 40),
      new THREE.MeshBasicMaterial({ color: 0x31ffd6, transparent: true, opacity: 0.32, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }),
    );
    ring.quaternion.setFromUnitVectors(forward, normal);
    ring.position.copy(normal.clone().multiplyScalar(0.002));
    group.add(glow, ring, core);
    globe.add(group);
    const node = { group, core, glow, ring, phase: index * 0.74, baseScale: glowScale, hub: Boolean(location.hub), boost: 0 };
    nodes.push(node);
    nodeByIndex.set(index, node);
  });

  function makeRoute(startIndex, endIndex, altitude, routeIndex) {
    const start = latLonToVector3(THREE, LOCATIONS[startIndex].lat, LOCATIONS[startIndex].lon, 1.025);
    const end = latLonToVector3(THREE, LOCATIONS[endIndex].lat, LOCATIONS[endIndex].lon, 1.025);
    const midpoint = start.clone().add(end).normalize().multiplyScalar(1 + altitude);
    const curve = new THREE.QuadraticBezierCurve3(start, midpoint, end);
    const color = [0x17edf5, 0x31ffd6, 0x45b9ff][routeIndex % 3];
    const tube = new THREE.Mesh(
      new THREE.TubeGeometry(curve, 52, routeIndex < 2 ? 0.005 : 0.0033, 5, false),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: routeIndex < 2 ? 0.38 : 0.24, blending: THREE.AdditiveBlending, depthWrite: false }),
    );
    globe.add(tube);
    const packet = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture, color, transparent: true, opacity: 0.92, blending: THREE.AdditiveBlending, depthWrite: false }));
    packet.scale.set(0.075, 0.075, 1);
    globe.add(packet);
    return { curve, packet, speed: 0.055 + routeIndex * 0.008, offset: routeIndex * 0.137, endIndex, material: tube.material };
  }
  const routes = ROUTES.map((route, index) => makeRoute(...route, index));

  const orbits = [];
  [
    [1.54, 0.53, 1.14, 0.20, 0.22],
    [1.48, 0.58, 1.72, -0.42, 0.15],
    [1.42, 0.47, 2.02, 0.78, 0.10],
  ].forEach(([rx, ry, rotX, rotZ, opacity], index) => {
    const group = new THREE.Group();
    group.rotation.set(rotX, index * 0.12, rotZ);
    stage.add(group);
    const points = [];
    for (let step = 0; step <= 120; step += 1) {
      const angle = step / 120 * Math.PI * 2;
      points.push(new THREE.Vector3(rx * Math.cos(angle), ry * Math.sin(angle), 0));
    }
    group.add(new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: index === 1 ? 0x31ffd6 : 0x17edf5, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false }),
    ));
    const packet = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture, color: 0xd8ffff, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false }));
    packet.scale.set(0.058, 0.058, 1);
    group.add(packet);
    orbits.push({ group, packet, rx, ry, speed: 0.08 - index * 0.014, phase: index * 2.1 });
  });

  const pointerTarget = new THREE.Vector2();
  const pointerCurrent = new THREE.Vector2();
  let dragging = false;
  let previousPointerX = 0;
  let previousPointerY = 0;

  function onPointerMove(event) {
    const rect = container.getBoundingClientRect();
    pointerTarget.x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 2 - 1;
    pointerTarget.y = -(((event.clientY - rect.top) / Math.max(rect.height, 1)) * 2 - 1);
    if (!dragging) return;
    globe.rotation.y += (event.clientX - previousPointerX) * 0.006;
    globe.rotation.x += (event.clientY - previousPointerY) * 0.004;
    globe.rotation.x = THREE.MathUtils.clamp(globe.rotation.x, -0.7, 0.7);
    previousPointerX = event.clientX;
    previousPointerY = event.clientY;
  }
  function onPointerDown(event) {
    dragging = true;
    previousPointerX = event.clientX;
    previousPointerY = event.clientY;
    container.classList.add("is-dragging");
    container.setPointerCapture?.(event.pointerId);
  }
  function onPointerUp(event) {
    dragging = false;
    container.classList.remove("is-dragging");
    container.releasePointerCapture?.(event.pointerId);
  }
  container.addEventListener("pointermove", onPointerMove);
  container.addEventListener("pointerdown", onPointerDown);
  container.addEventListener("pointerup", onPointerUp);
  container.addEventListener("pointercancel", onPointerUp);
  container.addEventListener("pointerleave", () => { if (!dragging) pointerTarget.set(0, 0); });

  const resize = () => {
    const rect = container.getBoundingClientRect();
    renderer.setSize(Math.max(rect.width, 1), Math.max(rect.height, 1), false);
    camera.aspect = Math.max(rect.width, 1) / Math.max(rect.height, 1);
    camera.updateProjectionMatrix();
  };
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container);
  resize();

  let visible = true;
  const visibilityObserver = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }, { threshold: 0.02 });
  visibilityObserver.observe(container);

  const clock = new THREE.Clock();
  let rafId = 0;
  const temp = new THREE.Vector3();
  const animate = () => {
    rafId = requestAnimationFrame(animate);
    if (!visible) return;
    const elapsed = clock.getElapsedTime();
    if (!reducedMotion) {
      if (!dragging) globe.rotation.y += 0.00048;
      stage.position.y = Math.sin(elapsed * 0.55) * 0.018;
      pointerCurrent.lerp(pointerTarget, 0.035);
      stage.rotation.x = pointerCurrent.y * 0.034;
      stage.rotation.z = -pointerCurrent.x * 0.026;
      atmosphereMaterial.uniforms.intensity.value = 0.78 + Math.sin(elapsed * 0.62) * 0.07;
      halo.material.opacity = 0.014 + (Math.sin(elapsed * 0.48) + 1) * 0.004;
      surfacePoints.rotation.y -= 0.00012;
      nodes.forEach((node, index) => {
        node.boost *= 0.92;
        const wave = 0.5 + 0.5 * Math.sin(elapsed * (node.hub ? 1.25 : 1.55) + node.phase);
        node.core.scale.setScalar(0.88 + wave * 0.22 + node.boost * 0.18);
        const scale = node.baseScale * (0.94 + wave * 0.15 + node.boost * 0.18);
        node.glow.scale.set(scale, scale, 1);
        node.glow.material.opacity = (node.hub ? 0.42 : 0.24) + wave * (node.hub ? 0.34 : 0.22);
        node.ring.scale.setScalar(0.92 + wave * 0.2);
        node.ring.material.opacity = 0.10 + wave * 0.24;
        node.ring.rotation.z = elapsed * 0.12 * (index % 2 ? -1 : 1);
      });
      routes.forEach((route, index) => {
        const t = (elapsed * route.speed + route.offset) % 1;
        route.packet.position.copy(route.curve.getPointAt(t, temp));
        const pulse = 0.84 + Math.sin(t * Math.PI * 8) * 0.12;
        route.packet.scale.setScalar(0.075 * pulse);
        route.material.opacity = 0.18 + (0.5 + 0.5 * Math.sin(elapsed * 0.5 + index)) * 0.22;
        if (t > 0.86) nodeByIndex.get(route.endIndex).boost = Math.max(nodeByIndex.get(route.endIndex).boost, (t - 0.86) / 0.14);
      });
      orbits.forEach((orbit, index) => {
        orbit.group.rotation.z += (index % 2 ? -1 : 1) * 0.0009;
        const angle = elapsed * orbit.speed + orbit.phase;
        orbit.packet.position.set(orbit.rx * Math.cos(angle), orbit.ry * Math.sin(angle), 0);
      });
    }
    renderer.render(scene, camera);
  };
  animate();

  return {
    destroy() {
      cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      visibilityObserver.disconnect();
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerdown", onPointerDown);
      container.removeEventListener("pointerup", onPointerUp);
      container.removeEventListener("pointercancel", onPointerUp);
      scene.traverse((object) => {
        object.geometry?.dispose?.();
        if (Array.isArray(object.material)) object.material.forEach((material) => material?.dispose?.());
        else object.material?.dispose?.();
      });
      glowTexture.dispose();
      renderer.dispose();
    },
  };
}

export async function initializeDashboardGlobe() {
  const container = document.querySelector("#view-dashboard .dashboard-globe");
  if (!container || activeGlobe) return;
  const legacyMarkup = container.innerHTML;
  try {
    const THREE = await import(THREE_MODULE_URL);
    installStylesheet();
    container.classList.add("three-globe-active");
    container.replaceChildren();
    activeGlobe = createDashboardGlobe(THREE, container);
    console.info("[Dashboard] Globo Three.js interactivo activo.");
  } catch (error) {
    container.classList.remove("three-globe-active");
    container.innerHTML = legacyMarkup;
    console.warn("[Dashboard] No se pudo iniciar el globo Three.js; se conserva el planeta CSS.", error);
  }
}

window.addEventListener("beforeunload", () => activeGlobe?.destroy?.(), { once: true });
