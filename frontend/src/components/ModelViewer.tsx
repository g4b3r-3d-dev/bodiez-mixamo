import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

type ViewName = 'perspective' | 'front' | 'side' | 'back'

type Props = {
  url: string | null
  wireframe: boolean
  skeleton: boolean
  preserveCamera?: boolean
  anatomicalView?: boolean
  viewRequest: { name: ViewName; nonce: number }
  onViewerError?: (message: string | null) => void
}

function disposeObject(root: THREE.Object3D) {
  const textures = new Set<THREE.Texture>()
  root.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return
    child.geometry?.dispose()
    const materials = Array.isArray(child.material) ? child.material : [child.material]
    materials.forEach((material) => {
      Object.values(material).forEach((value) => {
        if (value instanceof THREE.Texture) textures.add(value)
      })
      material.dispose()
    })
    if (child instanceof THREE.SkinnedMesh) child.skeleton.dispose()
  })
  textures.forEach((texture) => texture.dispose())
}

export default function ModelViewer({ url, wireframe, skeleton, preserveCamera = false, anatomicalView = false, viewRequest, onViewerError }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const sceneRef = useRef<THREE.Scene | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const controlsRef = useRef<OrbitControls | null>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const modelRef = useRef<THREE.Object3D | null>(null)
  const helperRef = useRef<THREE.SkeletonHelper | null>(null)
  const boundsRef = useRef<{ center: THREE.Vector3; size: THREE.Vector3 } | null>(null)
  const [loading, setLoading] = useState(false)
  const bodyFrameRef = useRef({front: new THREE.Vector3(0,0,1), right: new THREE.Vector3(1,0,0), up: new THREE.Vector3(0,1,0)})
  const displayRef = useRef({skeleton, wireframe, viewRequest})
  displayRef.current = {skeleton, wireframe, viewRequest}

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 10000)
    camera.position.set(2.6, 1.8, 3.4)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.05
    host.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.07
    controls.screenSpacePanning = true

    scene.add(new THREE.HemisphereLight(0xeaf0ff, 0x272a34, 2.2))
    const key = new THREE.DirectionalLight(0xffffff, 2.8)
    key.position.set(4, 6, 5)
    scene.add(key)
    const rim = new THREE.DirectionalLight(0x9d8cff, 1.4)
    rim.position.set(-4, 3, -5)
    scene.add(rim)
    const grid = new THREE.GridHelper(8, 16, 0x495064, 0x252a35)
    scene.add(grid)

    sceneRef.current = scene
    cameraRef.current = camera
    controlsRef.current = controls
    rendererRef.current = renderer

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

    let frame = 0
    const animate = () => {
      controls.update()
      renderer.render(scene, camera)
      frame = requestAnimationFrame(animate)
    }
    animate()

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      controls.dispose()
      if (modelRef.current) disposeObject(modelRef.current)
      renderer.dispose()
      renderer.domElement.remove()
      sceneRef.current = null
      cameraRef.current = null
      controlsRef.current = null
      rendererRef.current = null
      modelRef.current = null
      helperRef.current = null
      boundsRef.current = null
    }
  }, [])

  useEffect(() => {
    const scene = sceneRef.current
    if (!scene) return
    const keepCamera = preserveCamera && boundsRef.current !== null

    if (modelRef.current) {
      scene.remove(modelRef.current)
      disposeObject(modelRef.current)
      modelRef.current = null
    }
    if (helperRef.current) {
      scene.remove(helperRef.current)
      helperRef.current.geometry.dispose()
      const materials = Array.isArray(helperRef.current.material)
        ? helperRef.current.material : [helperRef.current.material]
      materials.forEach((material) => material.dispose())
      helperRef.current = null
    }
    boundsRef.current = null
    if (!url) return

    setLoading(true)
    onViewerError?.(null)
    const loader = new GLTFLoader()
    let cancelled = false
    loader.load(
      url,
      (gltf) => {
        if (cancelled) {
          disposeObject(gltf.scene)
          return
        }
        scene.add(gltf.scene)
        modelRef.current = gltf.scene
        gltf.scene.updateMatrixWorld(true)
        gltf.scene.traverse((object) => {
          if (object instanceof THREE.SkinnedMesh) object.skeleton.update()
        })
        if (anatomicalView && !keepCamera) {
          const bones = new Map<string, THREE.Vector3>()
          gltf.scene.traverse((object) => {
            if (object instanceof THREE.Bone) bones.set(object.name.toLowerCase().replace(/[^a-z0-9]/g, '').replace(/^mixamorig/, ''), object.getWorldPosition(new THREE.Vector3()))
          })
          const head=bones.get('head'), hips=bones.get('hips'), left=bones.get('leftarm'), right=bones.get('rightarm')
          if (head && hips && left && right) {
            const up=head.clone().sub(hips).normalize(), lateral=left.clone().sub(right)
            lateral.addScaledVector(up,-lateral.dot(up)).normalize()
            bodyFrameRef.current={up, right:lateral, front:lateral.clone().cross(up).normalize()}
          }
        }
        const helper = new THREE.SkeletonHelper(gltf.scene)
        helper.visible = displayRef.current.skeleton
        helperRef.current = helper
        scene.add(helper)

        const box = new THREE.Box3().setFromObject(gltf.scene)
        const center = box.getCenter(new THREE.Vector3())
        const size = box.getSize(new THREE.Vector3())
        boundsRef.current = { center, size }
        setLoading(false)
        if (!keepCamera) applyView(displayRef.current.viewRequest.name)
      },
      undefined,
      (error) => {
        if (cancelled) return
        setLoading(false)
        onViewerError?.(`Falha ao carregar o GLB intermediário: ${error instanceof Error ? error.message : String(error)}`)
      },
    )

    return () => {
      cancelled = true
    }
    // skeleton visibility is handled separately; reloading only when the URL changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url])

  useEffect(() => {
    const model = modelRef.current
    if (!model) return
    model.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return
      const materials = Array.isArray(child.material) ? child.material : [child.material]
      materials.forEach((material) => {
        if ('wireframe' in material) {
          ;(material as THREE.MeshStandardMaterial).wireframe = wireframe
          material.needsUpdate = true
        }
      })
    })
  }, [wireframe])

  useEffect(() => {
    if (helperRef.current) helperRef.current.visible = skeleton
  }, [skeleton])

  function applyView(name: ViewName) {
    const camera = cameraRef.current
    const controls = controlsRef.current
    const bounds = boundsRef.current
    if (!camera || !controls || !bounds) return
    const { center, size } = bounds
    const maxDim = Math.max(size.x, size.y, size.z, 0.1)
    const fov = THREE.MathUtils.degToRad(camera.fov)
    const distance = (maxDim / (2 * Math.tan(fov / 2))) * 1.55
    const offset = new THREE.Vector3()
    const frame = bodyFrameRef.current
    camera.up.copy(frame.up)
    if (name === 'front') offset.copy(frame.front).multiplyScalar(distance)
    else if (name === 'back') offset.copy(frame.front).multiplyScalar(-distance)
    else if (name === 'side') offset.copy(frame.right).multiplyScalar(distance)
    else offset.addScaledVector(frame.right,distance*.7).addScaledVector(frame.up,distance*.45).addScaledVector(frame.front,distance*.85)
    camera.position.copy(center).add(offset)
    camera.near = Math.max(0.001, distance / 1000)
    camera.far = Math.max(100, distance * 20)
    camera.updateProjectionMatrix()
    controls.target.copy(center)
    controls.update()
  }

  useEffect(() => {
    applyView(viewRequest.name)
    // nonce makes repeating the same view intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewRequest.name, viewRequest.nonce])

  return (
    <div className="viewerHost" ref={hostRef}>
      {!url && (
        <div className="viewerEmpty">
          <div className="viewerOrb" />
          <strong>Nenhum personagem carregado</strong>
          <span>Importe FBX, GLB ou GLTF para gerar a visualização 3D.</span>
        </div>
      )}
      {loading && <div className="viewerLoading">Carregando GLB…</div>}
    </div>
  )
}
