import * as T from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export interface SceneState {
  doorOpen?: boolean; garagePosition?: string; fanOn?: boolean; lightOn?: boolean;
  brightness?: number; lightColor?: string;
}
export type HouseView = 'perspective' | 'plan' | 'entrance';

export function createHouseScene(host: HTMLDivElement, initial: SceneState, onLost: () => void) {
  const renderer = new T.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = T.PCFShadowMap;
  renderer.outputColorSpace = T.SRGBColorSpace;
  renderer.setClearColor(0xecebe5, 1);
  host.appendChild(renderer.domElement);
  const scene = new T.Scene();
  const camera = new T.PerspectiveCamera(36, 1, .1, 80);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, .5, 0);
  controls.enablePan = false;
  controls.enableDamping = true;
  controls.minDistance = 8;
  controls.maxDistance = 22;
  controls.maxPolarAngle = Math.PI / 2.12;
  const mats = new Map<string, T.MeshStandardMaterial>();
  function material(color: string) {
    if (!mats.has(color)) mats.set(color, new T.MeshStandardMaterial({ color, roughness: .85 }));
    return mats.get(color)!;
  }
  function box(w: number, h: number, d: number, color: string, x: number, y: number, z: number, parent: T.Object3D = scene) {
    const mesh = new T.Mesh(new T.BoxGeometry(w, h, d), material(color));
    mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true;
    parent.add(mesh); return mesh;
  }
  scene.add(new T.HemisphereLight(0xffffff, 0x8e917e, 2.6));
  const sun = new T.DirectionalLight(0xfff5e8, 3.6);
  sun.position.set(-4, 10, 7); sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, { left: -8, right: 8, top: 8, bottom: -8, near: .5, far: 30 });
  sun.shadow.normalBias = .035;
  scene.add(sun);
  box(10.2, .22, 7.7, '#d5d4cb', 0, -.25, 0);
  box(9.6, .14, 7.1, '#fbfaf6', 0, -.07, 0);
  box(6.2, .05, 6.7, '#ddcbb0', -1.5, .03, 0);
  for (let z = -3; z <= 3; z += .38) box(6.16, .008, .012, '#cbb798', -1.5, .06, z);
  box(2.7, .04, 6.7, '#cecec6', 3, .03, 0);
  // Cutaway walls leave the front and roof open for inspection.
  box(9.5, 2.15, .16, '#eeede7', 0, 1.07, -3.4);
  box(.16, 2.15, 6.8, '#e4e4dc', -4.7, 1.07, 0);
  box(.12, 1.2, 6.6, '#f5f4ef', 1.5, .6, 0);
  box(5.9, 1.05, .12, '#f5f4ef', -1.55, .525, -.8);
  box(.12, 1.15, 2.5, '#eeede7', -1.5, .575, -2.1);
  // Living room: woven rug, low sofa, timber table and a reading lamp.
  box(4.2, .025, 2.9, '#f5f0e4', -1.45, .09, 1.1);
  box(2.65, .42, .95, '#768878', -2, .35, 2.05);
  box(2.65, .72, .18, '#647766', -2, .65, 2.5);
  for (const x of [-3.28, -.72]) box(.18, .6, 1.05, '#647766', x, .47, 2.05);
  for (const x of [-2.75, -1.98, -1.2]) box(.7, .15, .7, '#93a28c', x, .63, 1.99);
  box(1.7, .14, .85, '#ad8154', -1.5, .58, .55);
  for (const x of [-2.1, -.9]) for (const z of [.3, .8]) box(.07, .48, .07, '#6b5745', x, .3, z);
  box(.45, .06, .32, '#e6e4d6', -1.9, .69, .5);
  box(.28, .07, .24, '#9b5e43', -1.3, .7, .5);
  box(.15, 1.7, .15, '#535c52', .6, .9, 2.25);
  const lamp = new T.Mesh(new T.CylinderGeometry(.4, .55, .38, 24), new T.MeshStandardMaterial({ color: '#e9e2cb', emissive: '#ffb64c', emissiveIntensity: 0 }));
  lamp.position.set(.6, 1.8, 2.25); scene.add(lamp);
  const lampLight = new T.PointLight('#ffd393', 0, 6, 2);
  lampLight.position.set(.6, 1.5, 2.25); scene.add(lampLight);
  // Bedroom and kitchen sit behind the low partition.
  box(1.8, .4, 1.8, '#b2a18c', -3.1, .25, -2);
  box(1.8, .12, 1.7, '#f3eee2', -3.1, .5, -2);
  box(1.85, .8, .12, '#9b795b', -3.1, .45, -2.95);
  box(1.6, .05, 1, '#aaa77e', -3.1, .59, -1.65);
  for (const x of [-3.55, -2.65]) box(.65, .15, .35, '#fffdf3', x, .65, -2.55);
  box(2.6, .85, .62, '#c7c8b4', 0, .45, -2.95);
  box(2.7, .09, .7, '#fcfaf3', 0, .91, -2.93);
  box(.65, .025, .4, '#7b8480', -.65, .97, -2.9);
  box(.55, .025, .4, '#4d534e', .6, .97, -2.9);
  box(.75, 1.65, .7, '#dcdfd6', .9, .85, -1.6);
  // Decorative windows and plants have no hardware control.
  box(.04, 1.2, 1.8, '#bfd0c8', -4.59, 1.35, -.8);
  box(.06, .06, 1.9, '#fdfcf6', -4.55, 1.35, -.8);
  box(.06, 1.25, .05, '#fdfcf6', -4.55, 1.35, -.8);
  for (const [x, z] of [[-4, 2.7], [.9, -.5]]) {
    const pot = new T.Mesh(new T.CylinderGeometry(.22, .16, .35, 12), material('#b58663'));
    pot.position.set(x, .25, z); scene.add(pot);
    for (let i = 0; i < 5; i++) {
      const leaf = new T.Mesh(new T.SphereGeometry(.25, 10, 8), material(i % 2 ? '#5f7855' : '#82946a'));
      leaf.scale.set(.55, 1.7, .7); leaf.position.set(x + Math.sin(i * 2) * .16, .6 + i * .06, z + Math.cos(i * 2) * .15); scene.add(leaf);
    }
  }
  // Garage, vehicle and independently reported garage panel.
  box(1.15, .4, 2.4, '#717d7e', 3, .48, -.4);
  box(1.03, .4, 1.1, '#a6b7b2', 3, .88, -.5);
  for (const x of [2.4, 3.6]) for (const z of [-1.15, .4]) box(.16, .35, .42, '#343b3a', x, .27, z);
  box(2.6, .1, .2, '#a6a699', 3, 1.95, 3.1);
  for (const x of [1.65, 4.35]) box(.12, 2, .15, '#acac9d', x, 1, 3.1);
  const garage = new T.Group(); scene.add(garage);
  for (let i = 0; i < 7; i++) box(2.5, .24, .09, '#9ca49b', 3, .17 + i * .26, 3.1, garage);
  // Entrance door pivots at its hinge. It represents the actuator report only.
  const door = new T.Group(); door.position.set(-3.65, 0, 3.25); scene.add(door);
  const doorPanel = box(.92, 1.9, .1, '#a57c55', .46, .95, 0, door);
  box(.06, .08, .14, '#494c40', .78, 1, .1, door);
  for (const x of [-3.73, -2.65]) box(.1, 2, .17, '#e5e0d1', x, 1, 3.25);
  box(1.18, .1, .17, '#e5e0d1', -3.2, 2, 3.25);
  // Table fan with a small animated rotor.
  box(.52, .08, .4, '#a6ada2', -.1, .13, -.1);
  box(.06, .5, .06, '#68736b', -.1, .4, -.1);
  const fan = new T.Group(); fan.position.set(-.1, .75, -.1); scene.add(fan);
  for (let i = 0; i < 3; i++) {
    const blade = box(.13, .5, .04, '#536f63', 0, .15, 0, fan); blade.rotation.z = i * Math.PI * 2 / 3;
  }
  const ring = new T.Mesh(new T.TorusGeometry(.39, .025, 8, 32), material('#8c998c'));
  ring.position.copy(fan.position); scene.add(ring);
  let state = initial, stopped = false, frame = 0, last = 0;
  let reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const motion = () => { reduced = media.matches; };
  media.addEventListener('change', motion);
  const lost = (event: Event) => { event.preventDefault(); stopped = true; cancelAnimationFrame(frame); onLost(); };
  renderer.domElement.addEventListener('webglcontextlost', lost);
  function view(which: HouseView) {
    camera.position.set(...(which === 'plan' ? [0, 17, .15] : which === 'entrance' ? [0, 6, 16] : [10, 10, 12]) as [number, number, number]);
    controls.target.set(0, .5, 0); controls.update();
  }
  view('perspective');
  const resize = () => {
    const { width, height } = host.getBoundingClientRect();
    if (!width || !height) return;
    camera.aspect = width / height; camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
  };
  const observer = new ResizeObserver(resize); observer.observe(host); resize();
  function update(next: SceneState) {
    state = next;
    door.rotation.y = next.doorOpen ? -Math.PI * .6 : 0;
    door.visible = next.doorOpen !== undefined;
    doorPanel.material = material('#a57c55');
    garage.visible = ['open', 'closed', 'moving'].includes(next.garagePosition || '');
    garage.position.y = next.garagePosition === 'open' ? 1.7 : next.garagePosition === 'moving' ? .8 : 0;
    const lit = next.lightOn === true;
    const color = typeof next.lightColor === 'string' && /^#[0-9a-f]{6}$/i.test(next.lightColor) ? next.lightColor : '#ffd393';
    (lamp.material as T.MeshStandardMaterial).emissive.set(color);
    (lamp.material as T.MeshStandardMaterial).emissiveIntensity = lit ? 1 : 0;
    lampLight.color.set(color); lampLight.intensity = lit ? 8 * (next.brightness === undefined ? .65 : next.brightness / 100) : 0;
  }
  update(initial);
  function animate(now: number) {
    if (stopped) return;
    frame = requestAnimationFrame(animate);
    if (document.hidden || now - last < 33) return;
    const delta = Math.min((now - last) / 1000, .1); last = now;
    if (state.fanOn && !reduced) fan.rotation.z -= delta * 5;
    controls.update(); renderer.render(scene, camera);
  }
  frame = requestAnimationFrame(animate);
  return { update, view, dispose() {
    stopped = true; cancelAnimationFrame(frame);
    observer.disconnect(); controls.dispose(); media.removeEventListener('change', motion);
    renderer.domElement.removeEventListener('webglcontextlost', lost);
    scene.traverse(object => { if (object instanceof T.Mesh) object.geometry.dispose(); });
    const materials = new Set<T.Material>(mats.values()); materials.add(lamp.material);
    for (const mat of materials) mat.dispose();
    renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
  } };
}
