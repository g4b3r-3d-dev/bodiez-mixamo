// Verify the breast field in the exported, skinned GLBs, including unaffected regions.
import fs from 'node:fs'
import assert from 'node:assert/strict'
import * as THREE from 'three'
import {vertices} from './geometry-utils.mjs'
const [beforePath,afterPath,preparedPath,markersPath,valueText]=process.argv.slice(2)
const info=JSON.parse(fs.readFileSync(preparedPath)).result.capabilities.breast_marker_info
const markers=JSON.parse(fs.readFileSync(markersPath)),value=Number(valueText)
const centers=['left','right'].map(s=>new THREE.Vector3().fromArray(markers[s]))
const up=new THREE.Vector3().fromArray(info.up),front=new THREE.Vector3().fromArray(info.front),left=new THREE.Vector3().fromArray(info.left)
const [before,after]=await Promise.all([vertices(beforePath),vertices(afterPath)])
let outside=0,outsideChanged=0,changed=0,maxOutside=0,directionErrors=0
const sides=[0,0]
const maxProjection=[0,0],minProjection=[0,0]
const maxLateral=[0,0],maxUp=[0,0],maxDown=[0,0]
for(const [name,points] of before){
 const actual=after.get(name)
 assert.equal(actual?.length,points.length)
 points.forEach((p,i)=>{
  const delta=actual[i].clone().sub(p)
  const inside=centers.map(center=>{
   const d=p.clone().sub(center)
   return (d.dot(left)/markers.radius)**2+(d.dot(up)/markers.radius)**2+(d.dot(front)/(markers.radius*.9))**2<1+1e-5
  })
  if(!inside.some(Boolean)){
   outside++;maxOutside=Math.max(maxOutside,delta.length())
   if(delta.length()>1e-5)outsideChanged++
  }
  if(delta.length()>1e-5){
   changed++;inside.forEach((hit,side)=>{if(hit){sides[side]++;const forward=delta.dot(front);maxProjection[side]=Math.max(maxProjection[side],forward);minProjection[side]=Math.min(minProjection[side],forward);maxLateral[side]=Math.max(maxLateral[side],Math.abs(delta.dot(left)));maxUp[side]=Math.max(maxUp[side],delta.dot(up));maxDown[side]=Math.max(maxDown[side],-delta.dot(up))}})
   if(delta.dot(front)*Math.sign(value)<-1e-6)directionErrors++
  }
 })
}
assert.equal(outsideChanged,0,'Vertices outside breast regions moved')
assert.equal(directionErrors,0,'Wrong enlargement/reduction direction')
if(value!==0)assert(sides.every(n=>n>0),'Both breasts must change')
else assert.equal(changed,0,'Restore did not return to baseline')
console.log(JSON.stringify({outside_vertices:outside,outside_changed_vertices:outsideChanged,max_outside_displacement:maxOutside,changed_vertices:changed,changed_per_side:sides,max_forward_per_side:maxProjection,min_forward_per_side:minProjection,max_lateral_per_side:maxLateral,max_up_per_side:maxUp,max_down_per_side:maxDown,direction_errors:directionErrors},null,2))
