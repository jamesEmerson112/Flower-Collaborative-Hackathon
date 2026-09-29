import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import LAYOUT from './layout.json';
import { createScenePlan } from './build.js';

// Composition units deliberately differ from the dimensions of the source CAD.

export function createWorkshop(viewport) {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, .05, 60);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.domElement.setAttribute('aria-label', '3D robot preview. Use the buttons below to change the view.');
  renderer.domElement.setAttribute('role', 'img');
  viewport.append(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.minDistance = 3.6;
  controls.maxDistance = 10;
  controls.maxPolarAngle = Math.PI * .51;
  const targetHeight = () => viewport.clientWidth < 520 ? .95 : 1.3;
  controls.target.set(0, targetHeight(), 0);
  scene.add(new THREE.HemisphereLight(0xffffee, 0x718076, 1.5));
  const key = new THREE.DirectionalLight(0xfffaef, 2.5);
  key.position.set(3, 6, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = key.shadow.camera.bottom = -3;
  key.shadow.camera.right = key.shadow.camera.top = 3;
  key.shadow.normalBias = .025;
  key.shadow.bias = -.0002;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xd7e4ff, 1.0);
  fill.position.set(-4, 3, -2);
  scene.add(fill);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.ShadowMaterial({ color: 0x637045, opacity: .16 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -.035;
  ground.receiveShadow = true;
  scene.add(ground);
  const plinth = new THREE.Mesh(new THREE.CylinderGeometry(1.35, 1.37, .06, 80), new THREE.MeshStandardMaterial({ color: 0xe1e7d2, roughness: .9 }));
  plinth.position.y = -.045;
  plinth.receiveShadow = true;
  scene.add(plinth);
  const robot = new THREE.Group();
  robot.name = 'Mixed supplier robot concept';
  robot.userData = { concept_only: true, units: 'visual composition; not physical dimensions', compatibility_verified: false };
  scene.add(robot);
  const loader = new GLTFLoader();
  const cache = new Map();
  let generation = 0, spread = false;
  const base = import.meta.env.BASE_URL;

  function asset(part) {
    if (!cache.has(part.id)) {
      const promise = loader.loadAsync(base + part.model).then(gltf => gltf.scene).catch(error => { cache.delete(part.id); throw error; });
      cache.set(part.id, promise);
    }
    return cache.get(part.id);
  }

  function place(group) {
    const p = group.userData.assembled_position;
    group.position.fromArray(p);
    if (spread) {
      group.position.x *= 1.45;
      group.position.y = 1.4 + (p[1] - 1.4) * 1.3;
    }
  }

  async function update(build, catalog) {
    const token = ++generation;
    // Keep the previous complete robot visible until the replacement is ready.
    const plan = createScenePlan(build, catalog, LAYOUT);
    const loaded = await Promise.all(plan.map(async placement => ({ ...placement, original: await asset(placement.part) })));
    if (token !== generation) return false;
    robot.clear();
    for (const { slot, slots, part, original, position, size, rotation } of loaded) {
      const mesh = original.clone(true);
      mesh.rotation.set(...rotation);
      mesh.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(mesh);
      const dimensions = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const target = size;
      // A wrapper scales in world axes after orienting the original part.
      const centered = new THREE.Group();
      mesh.position.sub(center);
      centered.add(mesh);
      centered.scale.set(...target.map((v, i) => v / Math.max(dimensions.getComponent(i), .0001)));
      const group = new THREE.Group();
      group.name = `${slot} · ${part.name}`;
      group.userData = { slot, slots, assembled_position: position, product_id: part.id, supplier: part.supplier, product_url: part.productUrl, source_url: part.sourceUrl, note: part.note, model_kind: part.modelKind, resized_for_concept: true };
      group.add(centered);
      group.traverse(child => { if (child.isMesh) { child.castShadow = true; child.receiveShadow = true; } });
      place(group);
      robot.add(group);
    }
    viewport.dataset.ready = 'true';
    viewport.dataset.parts = JSON.stringify(build.slots);
    viewport.dataset.placements = JSON.stringify(plan.map(({ slot, slots, part, position, size, rotation }) => ({ slot, slots, product_id: part.id, position, size, rotation })));
    return true;
  }

  function front() {
    camera.position.set(0, 2.3, camera.aspect < 1 ? 7.8 : 6.8);
    controls.target.set(0, targetHeight(), 0);
    controls.update();
  }
  function rotate(direction) {
    const offset = camera.position.clone().sub(controls.target);
    offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), direction * Math.PI / 6);
    camera.position.copy(controls.target).add(offset);
    controls.update();
  }
  const observer = new ResizeObserver(() => {
    const { width, height } = viewport.getBoundingClientRect();
    camera.aspect = width / Math.max(height, 1);
    controls.target.y = targetHeight();
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  });
  observer.observe(viewport);
  camera.position.set(3.6, 2.8, 6.2);
  controls.update();
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });

  return {
    update, front, rotate,
    toggleSpread() {
      spread = !spread;
      for (const group of robot.children) place(group);
      return spread;
    },
    async exportRobot() {
      // Export the assembled pose even while the inspection view is spread out.
      const copy = robot.clone(true);
      for (const group of copy.children) group.position.fromArray(group.userData.assembled_position);
      copy.updateMatrixWorld(true);
      return new GLTFExporter().parseAsync(copy, { binary: true, onlyVisible: true });
    },
  };
}
