// Compare exported skinning and morphs without browser-only texture loading.
import {vertices} from './geometry-utils.mjs'

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
