import { ChangeEvent, useEffect, useRef, useState } from 'react'
import { Bone, Box, CheckCircle2, FileUp, PlugZap, Rotate3D, Settings2 } from 'lucide-react'
import {
  absoluteAssetUrl, getSettings, saveBlenderPath, startAdaptPreparation, startAssetImport,
  startBlenderTest, startExistingPreparation, watchTask,
} from './api'
import InspectionPanel from './components/InspectionPanel'
import ModelViewer from './components/ModelViewer'
import PreparationPanel from './components/PreparationPanel'
import type { AdaptBaseOptions, AssetImportResult, BlenderConnectionResult, PreparationResult, TaskEvent } from './types'
import { isAssetImportResult, isBlenderConnectionResult, isPreparationResult } from './types'

type Tab = 'blender' | 'import' | 'prepare'
type ViewName = 'perspective' | 'front' | 'side' | 'back'
const modelExts = new Set(['fbx', 'glb', 'gltf'])
const baseExts = new Set(['fbx', 'glb', 'gltf', 'blend'])
const resourceExts = new Set(['bin', 'png', 'jpg', 'jpeg', 'webp', 'ktx2'])
const ext = (name: string) => name.split('.').pop()?.toLowerCase() ?? ''

function splitFiles(files: File[], allowedModels: Set<string>) {
  return {
    models: files.filter(f => allowedModels.has(ext(f.name))),
    resources: files.filter(f => resourceExts.has(ext(f.name))),
    unsupported: files.filter(f => !allowedModels.has(ext(f.name)) && !resourceExts.has(ext(f.name))),
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>('blender')
  const [blenderPath, setBlenderPath] = useState('')
  const [connection, setConnection] = useState<BlenderConnectionResult | null>(null)
  const [model, setModel] = useState<File | null>(null)
  const [resources, setResources] = useState<File[]>([])
  const [asset, setAsset] = useState<AssetImportResult | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [prepMode, setPrepMode] = useState<'existing_bound' | 'adapt_base'>('existing_bound')
  const [base, setBase] = useState<File | null>(null)
  const [baseResources, setBaseResources] = useState<File[]>([])
  const [prep, setPrep] = useState<PreparationResult | null>(null)
  const [options, setOptions] = useState<AdaptBaseOptions>({ scale: 1, offset_x: 0, offset_y: 0, offset_z: 0, rotation_z: 0 })
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState('Carregando serviço local...')
  const [logs, setLogs] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [wireframe, setWireframe] = useState(false)
  const [skeleton, setSkeleton] = useState(false)
  const [view, setView] = useState<{ name: ViewName; nonce: number }>({ name: 'perspective', nonce: 0 })
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    getSettings().then(s => {
      setBlenderPath(s.blender_path ?? s.detected_path ?? '')
      setStatus(s.blender_path || s.detected_path ? 'Blender configurado.' : 'Configure o caminho do Blender.')
    }).catch(e => setError(`Backend local indisponível: ${e.message}`))
    return () => socketRef.current?.close()
  }, [])

  function begin(message: string) {
    socketRef.current?.close(); setBusy(true); setProgress(0); setLogs([]); setError(null); setStatus(message)
  }

  function attach(taskId: string, success: (event: Extract<TaskEvent, { type: 'success' }>) => void) {
    const ws = watchTask(taskId, event => {
      if (event.type === 'progress') { setProgress(event.value); setStatus(event.message) }
      if (event.type === 'log') setLogs(v => [...v, `[${event.stream}] ${event.message}`])
      if (event.type === 'error') { setError(event.message); setStatus('Erro no processamento.'); setBusy(false); ws.close() }
      if (event.type === 'success') { setProgress(100); setStatus(event.message); setBusy(false); success(event); ws.close() }
    })
    ws.onerror = () => { setError('WebSocket com o backend foi interrompido.'); setBusy(false) }
    socketRef.current = ws
  }

  async function savePath() {
    try { const s = await saveBlenderPath(blenderPath); setBlenderPath(s.blender_path ?? blenderPath); setStatus('Caminho salvo.') }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  async function testBlender() {
    begin('Testando Blender e bpy...'); setConnection(null)
    try { const id = await startBlenderTest(blenderPath); attach(id, e => { if (isBlenderConnectionResult(e.result)) setConnection(e.result) }) }
    catch (e) { setBusy(false); setError(e instanceof Error ? e.message : String(e)) }
  }

  function chooseModel(e: ChangeEvent<HTMLInputElement>) {
    const { models, resources: deps, unsupported } = splitFiles(Array.from(e.target.files ?? []), modelExts)
    if (models.length !== 1 || unsupported.length) { setError('Selecione exatamente um FBX/GLB/GLTF e apenas dependências BIN/imagens suportadas.'); return }
    setModel(models[0]); setResources(deps); setError(null)
  }

  function chooseBase(e: ChangeEvent<HTMLInputElement>) {
    const { models, resources: deps, unsupported } = splitFiles(Array.from(e.target.files ?? []), baseExts)
    if (models.length !== 1 || unsupported.length) { setError('Selecione exatamente uma base FBX/GLB/GLTF/BLEND.'); return }
    if (ext(models[0].name) === 'blend' && deps.length) { setError('Envie .blend sem dependências externas adicionais.'); return }
    setBase(models[0]); setBaseResources(deps); setError(null)
  }

  async function importCharacter() {
    if (!model) return
    begin(`Importando ${model.name}...`); setAsset(null); setPrep(null); setPreview(null)
    try {
      const r = await startAssetImport(model, resources)
      attach(r.taskId, e => { if (isAssetImportResult(e.result)) { setAsset(e.result); setPreview(absoluteAssetUrl(e.result.preview_url)); setTab('import') } })
    } catch (e) { setBusy(false); setError(e instanceof Error ? e.message : String(e)) }
  }

  async function prepareBody() {
    if (!asset) { setError('Importe um personagem primeiro.'); return }
    if (prepMode === 'adapt_base' && !base) { setError('Selecione a base corporal.'); return }
    begin(prepMode === 'existing_bound' ? 'Validando skin Mixamo existente...' : 'Adaptando a base corporal...')
    try {
      const r = prepMode === 'existing_bound'
        ? await startExistingPreparation(asset.asset_id)
        : await startAdaptPreparation(asset.asset_id, base!, baseResources, options)
      attach(r.taskId, e => {
        if (isPreparationResult(e.result)) { setPrep(e.result); setPreview(absoluteAssetUrl(e.result.preview_url)); setTab('prepare') }
      })
    } catch (e) { setBusy(false); setError(e instanceof Error ? e.message : String(e)) }
  }

  const setCamera = (name: ViewName) => setView({ name, nonce: Date.now() })

  return <div className="app">
    <header><div className="brand"><Box size={20}/><div><b>Bodiez Local</b><span>Blender + Mixamo</span></div></div><nav>
      <button className={tab === 'blender' ? 'active' : ''} onClick={() => setTab('blender')}><PlugZap size={15}/>Blender</button>
      <button className={tab === 'import' ? 'active' : ''} onClick={() => setTab('import')}><FileUp size={15}/>Importar</button>
      <button className={tab === 'prepare' ? 'active' : ''} onClick={() => setTab('prepare')} disabled={!asset}><Bone size={15}/>Preparar base</button>
    </nav><div className="statusPill">{busy ? `${progress}%` : prep?.preparation.ready_for_body_customization ? 'Base pronta' : asset ? 'Modelo carregado' : connection ? 'Blender OK' : 'Local'}</div></header>

    <main>
      <aside className="left">
        {tab === 'blender' && <section><h2><Settings2 size={16}/>Conexão com Blender</h2><label>Caminho do executável<input value={blenderPath} onChange={e => setBlenderPath(e.target.value)} placeholder="/usr/bin/blender" /></label><div className="actions"><button onClick={savePath}>Salvar</button><button className="primary" onClick={testBlender} disabled={!blenderPath || busy}>Testar Blender</button></div>{connection && <div className="success"><CheckCircle2 size={16}/><div><b>Blender {connection.version}</b><span>Python {connection.python_version} · bpy executado</span></div></div>}</section>}

        {tab === 'import' && <section><h2><FileUp size={16}/>Importação</h2><p>O original é preservado e o Blender trabalha em uma cópia.</p><label className="drop">Personagem + dependências<input type="file" multiple onChange={chooseModel} accept=".fbx,.glb,.gltf,.bin,.png,.jpg,.jpeg,.webp,.ktx2"/><b>{model?.name ?? 'Selecionar arquivos'}</b><span>{resources.length} dependência(s)</span></label><button className="primary full" onClick={importCharacter} disabled={!model || busy}>Importar e inspecionar</button>{asset && <div className="success"><CheckCircle2 size={16}/><div><b>{asset.original_name}</b><span>{asset.inspection.summary.armature_count} armature(s), {asset.inspection.summary.shape_key_count} shape key(s)</span></div></div>}</section>}

        {tab === 'prepare' && <section><h2><Bone size={16}/>Preparação corporal</h2><p>Transferência de pesos e retargeting são operações diferentes. Esta etapa não retargeteia animações.</p><div className="segmented"><button className={prepMode === 'existing_bound' ? 'active' : ''} onClick={() => setPrepMode('existing_bound')}>Malha já skinnada</button><button className={prepMode === 'adapt_base' ? 'active' : ''} onClick={() => setPrepMode('adapt_base')}>Adaptar base</button></div>{prepMode === 'adapt_base' && <><label className="drop">Base corporal<input type="file" multiple onChange={chooseBase} accept=".fbx,.glb,.gltf,.blend,.bin,.png,.jpg,.jpeg,.webp,.ktx2"/><b>{base?.name ?? 'Selecionar base'}</b><span>{baseResources.length} dependência(s)</span></label><div className="gridInputs">{([['scale','Escala'],['offset_x','X'],['offset_y','Y'],['offset_z','Z'],['rotation_z','Rot. Z']] as const).map(([key,label]) => <label key={key}>{label}<input type="number" step={key === 'scale' ? .05 : .1} value={options[key]} onChange={e => setOptions(v => ({ ...v, [key]: Number(e.target.value) }))}/></label>)}</div></>}<button className="primary full" onClick={prepareBody} disabled={busy || !asset}>Executar preparação e testes</button>{prep && <a className="download" href={absoluteAssetUrl(prep.blend_url)}>Abrir prepared.blend</a>}</section>}

        <section className="progress"><span>{status}</span><div><i style={{ width: `${progress}%` }}/></div>{error && <p className="error">{error}</p>}{logs.length > 0 && <details><summary>Logs ({logs.length})</summary><pre>{logs.slice(-60).join('\n')}</pre></details>}</section>
      </aside>

      <section className="viewer"><div className="toolbar"><button onClick={() => setCamera('perspective')}><Rotate3D size={14}/>Perspectiva</button><button onClick={() => setCamera('front')}>Frente</button><button onClick={() => setCamera('side')}>Lado</button><button onClick={() => setCamera('back')}>Trás</button><label><input type="checkbox" checked={wireframe} onChange={e => setWireframe(e.target.checked)}/>Wireframe</label><label><input type="checkbox" checked={skeleton} onChange={e => setSkeleton(e.target.checked)}/>Esqueleto</label></div><ModelViewer url={preview} wireframe={wireframe} skeleton={skeleton} viewRequest={view} onViewerError={m => m && setError(m)}/></section>

      <aside className="right"><h2>{tab === 'prepare' ? 'Validação da base' : 'Inspeção Blender'}</h2>{tab === 'prepare' ? <PreparationPanel report={prep?.preparation ?? null}/> : <InspectionPanel report={asset?.inspection ?? null}/>}</aside>
    </main>
  </div>
}
