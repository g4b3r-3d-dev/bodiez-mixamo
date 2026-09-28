import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

export type MorphApplication = {
  mesh: string
  key: string
  value: number
}

type Props = {
  url: string | null
  morphApplications: MorphApplication[]
  showSkeleton?: boolean
  onError?: (message: string | null) => void
  onMorphReport?: (report: { requested: number; matched: number }) => void
}

function disposeObject(root: THREE.Object3D) {
  root.traverse((object) => {
    const mesh = object as THREE.Mesh
    if (mesh.geometry) mesh.geometry.dispose()
    const material = (mesh as any).material as THREE.Material | THREE.Material[] | undefined
    if (Array.isArray(material)) material.forEach((item) => item.dispose())
    else material?.dispose()
  })
}

export default function Stage6Viewer({
  url,
  morphApplications,
  showSkeleton = true,
  onError,
  onMorphReport,
}: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const sceneRef = useRef<THREE.Scene | null>(null)
  const modelRef = useRef<THREE.Object3D | null>(null)
  const skeletonRef = useRef<THREE.SkeletonHelper | null>(null)
  const controlsRef = useRef<OrbitControls | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const framedRef = useRef(false)
  const loadTokenRef = useRef(0)
  const applicationsRef = useRef(morphApplications)
  const reportRef = useRef(onMorphReport)

  applicationsRef.current = morphApplications
  reportRef.current = onMorphReport

  const applyMorphs = () => {
    const model = modelRef.current
    if (!model) {
      reportRef.current?.({ requested: applicationsRef.current.length, matched: 0 })
      return
    }
    const meshes: Array<THREE.Mesh & {
      morphTargetDictionary?: Record<string, number>
      morphTargetInfluences?: number[]
    }> = []
    model.traverse((object) => {
      const mesh = object as typeof meshes[number]
      if (mesh.isMesh && mesh.morphTargetDictionary && mesh.morphTargetInfluences) {
        mesh.morphTargetInfluences.fill(0)
        meshes.push(mesh)
      }
    })

    let matched = 0
    for (const application of applicationsRef.current) {
      let applied = false
      const preferred = meshes.filter((mesh) => mesh.name === application.mesh)
      const candidates = preferred.length ? preferred : meshes
      for (const mesh of candidates) {
        const index = mesh.morphTargetDictionary?.[application.key]
        if (index === undefined || !mesh.morphTargetInfluences) continue
        mesh.morphTargetInfluences[index] = application.value
        applied = true
      }
      if (applied) matched += 1
    }
    reportRef.current?.({ requested: applicationsRef.current.length, matched })
  }

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0f1319)
    sceneRef.current = scene

    const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 2000)
    camera.position.set(2.2, 1.5, 3.2)
    cameraRef.current = camera

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    host.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controlsRef.current = controls

    scene.add(new THREE.HemisphereLight(0xffffff, 0x20252e, 2.2))
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.5)
    keyLight.position.set(3, 5, 4)
    scene.add(keyLight)
    scene.add(new THREE.GridHelper(8, 16, 0x39414d, 0x242a33))

    const resize = () => {
      const width = Math.max(1, host.clientWidth)
      const height = Math.max(1, host.clientHeight)
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(host)
    resize()

    let disposed = false
    let frame = 0
    const animate = () => {
      if (disposed) return
      controls.update()
      renderer.render(scene, camera)
      frame = requestAnimationFrame(animate)
    }
    animate()

    return () => {
      disposed = true
      loadTokenRef.current += 1
      cancelAnimationFrame(frame)
      observer.disconnect()
      controls.dispose()
      skeletonRef.current?.removeFromParent()
      if (modelRef.current) {
        modelRef.current.removeFromParent()
        disposeObject(modelRef.current)
      }
      renderer.dispose()
      renderer.domElement.remove()
      modelRef.current = null
      sceneRef.current = null
      controlsRef.current = null
      cameraRef.current = null
    }
  }, [])

  useEffect(() => {
    const scene = sceneRef.current
    const controls = controlsRef.current
    const camera = cameraRef.current
    if (!scene || !controls || !camera) return

    const token = ++loadTokenRef.current
    if (!url) {
      skeletonRef.current?.removeFromParent()
      skeletonRef.current = null
      if (modelRef.current) {
        modelRef.current.removeFromParent()
        disposeObject(modelRef.current)
        modelRef.current = null
      }
      onMorphReport?.({ requested: morphApplications.length, matched: 0 })
      return
    }

    new GLTFLoader().load(
      url,
      (gltf) => {
        if (token !== loadTokenRef.current) {
          disposeObject(gltf.scene)
          return
        }
        const old = modelRef.current
        skeletonRef.current?.removeFromParent()
        skeletonRef.current = null
        if (old) {
          old.removeFromParent()
          disposeObject(old)
        }
        modelRef.current = gltf.scene
        scene.add(gltf.scene)

        if (!framedRef.current) {
          const box = new THREE.Box3().setFromObject(gltf.scene)
          const size = box.getSize(new THREE.Vector3())
          const center = box.getCenter(new THREE.Vector3())
          const radius = Math.max(size.length() * 0.55, 0.5)
          controls.target.copy(center)
          camera.position.set(center.x + radius * 1.1, center.y + radius * 0.5, center.z + radius * 1.7)
          camera.near = Math.max(radius / 1000, 0.001)
          camera.far = radius * 30
          camera.updateProjectionMatrix()
          controls.update()
          framedRef.current = true
        }

        if (showSkeleton) {
          const helper = new THREE.SkeletonHelper(gltf.scene)
          skeletonRef.current = helper
          scene.add(helper)
        }
        applyMorphs()
        onError?.(null)
      },
      undefined,
      (error) => onError?.(`Falha ao abrir a prévia GLB: ${String(error)}`),
    )
  }, [url, showSkeleton])

  useEffect(() => {
    applyMorphs()
  }, [morphApplications])

  return <div className="stage6ViewerHost" ref={hostRef} />
}
