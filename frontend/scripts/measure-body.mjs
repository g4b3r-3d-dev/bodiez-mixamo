// Evaluate the exported GLB with the same Three.js loader and skinning as the viewer.
// Materials are omitted only to allow geometry validation without a browser or GPU.
import fs from 'node:fs'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

async function vertices(path) {
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
  const points = new Map()
  gltf.scene.traverse(o => {
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
const [beforePath, afterPath] = process.argv.slice(2)
if (!beforePath || !afterPath) throw new Error('Usage: node scripts/measure-body.mjs before.glb after.glb')
const [before, after] = await Promise.all([vertices(beforePath), vertices(afterPath)])
let count = 0, changed = 0, sum = 0, maximum = 0
const meshes = []
for (const [name, points] of before) {
  const other = after.get(name)
  if (!other || points.length !== other.length) throw new Error(`Incompatible topology for ${name}`)
  let localMax = 0
  points.forEach((p, i) => {
    const d = p.distanceTo(other[i]); count++; sum += d
    if (d > 1e-6) changed++
    maximum = Math.max(maximum, d); localMax = Math.max(localMax, d)
  })
  meshes.push({name, vertices: points.length, max_displacement: localMax})
}
if (!count) throw new Error('No skinned vertices')
console.log(JSON.stringify({vertices:count, changed_vertices:changed, mean_displacement:sum/count, max_displacement:maximum, meshes}, null, 2))
