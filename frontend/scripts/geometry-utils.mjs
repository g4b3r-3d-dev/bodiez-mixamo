// Evaluate the exported GLB with the same Three.js loader and skinning as the viewer.
// Materials are omitted only to allow geometry validation without a browser or GPU.
import fs from 'node:fs'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

export async function loadGeometry(path) {
  const original = fs.readFileSync(path)
  const jsonLength = original.readUInt32LE(12)
  const data = JSON.parse(original.subarray(20, 20 + jsonLength).toString())
  for (const mesh of data.meshes ?? []) for (const p of mesh.primitives) delete p.material
  delete data.materials; delete data.images; delete data.textures
  const encoded = Buffer.from(JSON.stringify(data))
  const json = Buffer.alloc(Math.ceil(encoded.length / 4) * 4, 32); encoded.copy(json)
  const binary = original.subarray(20 + jsonLength)
  const out = Buffer.alloc(20 + json.length + binary.length)
  original.copy(out, 0, 0, 12); out.writeUInt32LE(out.length, 8)
  out.writeUInt32LE(json.length, 12); out.writeUInt32LE(0x4e4f534a, 16)
  json.copy(out, 20); binary.copy(out, 20 + json.length)
  const gltf = await new GLTFLoader().parseAsync(out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength), '')
  gltf.scene.updateMatrixWorld(true)
  return gltf.scene
}

export async function vertices(path) {
  const scene=await loadGeometry(path)
  const points = new Map()
  scene.traverse(o => {
    if (!o.isSkinnedMesh) return
    o.skeleton.update()
    const list = []
    for (let i = 0; i < o.geometry.attributes.position.count; i++) {
      list.push(o.getVertexPosition(i, new THREE.Vector3()).applyMatrix4(o.matrixWorld))
    }
    points.set(o.name, list)
  })
  return points
}
