// Deterministic fixture clicks via the same Three.js raycaster used by the viewer.
// These sample locations belong to the female validation fixture, not auto-detection.
import fs from 'node:fs'
import * as THREE from 'three'
import {loadGeometry} from './geometry-utils.mjs'
const [modelPath,preparedPath] = process.argv.slice(2)
const prepared=JSON.parse(fs.readFileSync(preparedPath))
const info=prepared.result.capabilities.breast_marker_info
const scene=await loadGeometry(modelPath)
scene.traverse(o=>{if(o.isSkinnedMesh)o.skeleton.update()})
const origin=new THREE.Vector3().fromArray(info.origin),up=new THREE.Vector3().fromArray(info.up),front=new THREE.Vector3().fromArray(info.front),left=new THREE.Vector3().fromArray(info.left)
const raycaster=new THREE.Raycaster()
const result={radius:info.radius_default}
for(const [side,sign] of [['left',1],['right',-1]]){
 const target=origin.clone().addScaledVector(up,(info.chest_max-info.chest_min)*.43+info.chest_min-origin.dot(up)).addScaledVector(left,info.height*.055*sign)
 raycaster.set(target.addScaledVector(front,info.height),front.clone().negate())
 const hit=raycaster.intersectObject(scene,true).find(x=>x.object.isSkinnedMesh)
 if(!hit)throw new Error(`No surface hit on ${side}`)
 result[side]=hit.point.toArray()
}
console.log(JSON.stringify(result,null,2))
