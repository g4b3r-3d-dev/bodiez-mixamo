import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, Bone, Box, CheckCircle2, CircleAlert, Cuboid, Download, Eye, FileUp, Link2, PlugZap,
  Rotate3D, Save, Search, Settings2, ShieldCheck, SlidersHorizontal, TerminalSquare, Upload, Waypoints,
} from 'lucide-react'
import {
  absoluteAssetUrl, getSettings, saveBlenderPath, startAdaptPreparation, startAssetImport,
  startBlenderTest, startExistingPreparation, watchTask,
} from './api'
import ModelViewer from './components/ModelViewer'
import InspectionPanel from './components/InspectionPanel'
import PreparationPanel from './components/PreparationPanel'
import type {
  AdaptBaseOptions, AssetImportResult, BlenderConnectionResult, InspectionReport, PreparationResult, TaskEvent,
} from './types'
import { isAssetImportResult, isBlenderConnectionResult, isPreparationResult } from './types'

type LogLine = { level: string; stream: string; message: string }
type AppMode = 'import' | 'prepare' | 'blender'
type PreparationMode = 'existing_bound' | 'adapt_base'
type ViewName = 'perspective' | 'front' | 'side' | 'back'

const MODEL_EXTS = new Set(['fbx', 'glb', 'gltf'])
const BASE_MODEL_EXTS = new Set(['fbx', 'glb', 'gltf', 'blend'])
const RESOURCE_EXTS = new Set(['bin', 'png', 'jpg', 'jpeg', 'webp', 'ktx2'])

function extension(name: string) {
  return name.split('.').pop()?.toLowerCase() ?? ''
}

function classifyFiles(files: File[], modelExtensions: Set<string>) {
  return {
    models: files.filter((file) => modelExtensions.has(extension(file.name))),
    resources: files.filter((file) => RESOURCE_EXTS.has(extension(file.name))),
    unsupported: files.filter((file) => !modelExtensions.has(extension(file.name)) && !RESOURCE_EXTS.has(extension(file.name))),
  }
}

export default function App() {
  const [mode, setMode] = useState<AppMode>('import')
  const [blenderPath, setBlenderPath] = useState('')
  const [detectedPath, setDetectedPath] = useState<string | null>(null)
  const [connectionResult, setConnectionResult] = useState<BlenderConnectionResult | null>(null)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState('Carregando configuração local...')
  const [logs, setLogs] = useState<LogLine[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [selectedModel, setSelectedModel] = useState<File | null>(null)
  const [selectedResources, setSelectedResources] = useState<File[]>([])
  const [assetResult, setAssetResult] = useState<AssetImportResult | null>(null)
  const [inspection, setInspection] = useState<InspectionReport | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const [preparationMode, setPreparationMode] = useState<PreparationMode>('existing_bound')
  const [baseModel, setBaseModel] = useState<File | null>(null)
  const [baseResources, setBaseResources] = useState<File[]>([])
  const [adaptOptions, setAdaptOptions] = useState<AdaptBaseOptions>({ scale: 1, offset_x: 0, offset_y: 0, offset_z: 0, rotation_z: 0 })
  const [preparationResult, setPreparationResult] = useState<PreparationResult | null>(null)
  const [preparedPreviewUrl, setPreparedPreviewUrl] = useState<string | null>(null)

  const [wireframe, setWireframe] = useState(false)
  const [showSkeleton, setShowSkeleton] = useState(false)
  const [viewRequest, setViewRequest] = useState<{ name: ViewName; nonce: number }>({ name: 'perspective', nonce: 0 })
  const [viewerError, setViewerError] = useState<string | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const baseInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    getSettings()
      .then((settings) => {
        setBlenderPath(settings.blender_path ?? settings.detected_path ?? '')
        setDetectedPath(settings.detected_path)
        setStatus(settings.blender_path || settings.detected_path ? 'Blender configurado. Importe um personagem.' : 'Configure o Blender antes de importar.')
      })
      .catch((err) => {
        setError(`Não foi possível acessar o backend local: ${err.message}`)
        setStatus('Backend indisponível.')
      })

    return () => socketRef.current?.close()
  }, [])

  const stateLabel = useMemo(() => {
    if (busy) return 'Processando'
    if (error || viewerError) return 'Atenção'
    if (preparationResult?.preparation.ready_for_body_customization) return 'Base pronta'
    if (preparationResult) return 'Revisar base'
    if (assetResult) return 'Modelo pronto'
    if (connectionResult) return 'Blender OK'
    return blenderPath ? 'Pronto' : 'Configurar'
  }, [assetResult, blenderPath, busy, connectionResult, error, preparationResult, viewerError])

  const currentPreview = mode === 'prepare' && preparedPreviewUrl ? preparedPreviewUrl : previewUrl

  function resetTaskUi(message: string) {
    socketRef.current?.close()
    setBusy(true)
    setError(null)
    setViewerError(null)
    setLogs([])
    setProgress(0)
    setStatus(message)
  }

  function attachTaskSocket(taskId: string, onSuccess: (event: Extract<TaskEvent, { type: 'success' }>, socket: WebSocket) => void) {
    const socket = watchTask(taskId, (event) => {
      if (event.type === 'progress') {
        setProgress(event.value)
        setStatus(event.message)
      } else if (event.type === 'log') {
        setLogs((current) => [...current, event])
      } else if (event.type === 'success') {
        setProgress(100)
        setStatus(event.message)
        setBusy(false)
        onSuccess(event, socket)
        socket.close()
      } else if (event.type === 'error') {
        setError(event.message)
        setStatus('Processamento concluído com erro.')
        setBusy(false)
        socket.close()
      }
    })
    socket.onerror = () => {
      setError('A conexão WebSocket com o backend foi interrompida.')
      setBusy(false)
    }
    socketRef.current = socket
  }

  async function handleSave() {
    setError(null)
    try {
      const settings = await saveBlenderPath(blenderPath)
      setBlenderPath(settings.blender_path ?? blenderPath)
      setStatus('Caminho do Blender salvo localmente.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao salvar o caminho.')
    }
  }

  async function handleTest() {
    resetTaskUi('Criando tarefa de diagnóstico...')
    setConnectionResult(null)
    try {
      const taskId = await startBlenderTest(blenderPath)
      attachTaskSocket(taskId, (event) => {
        if (isBlenderConnectionResult(event.result)) setConnectionResult(event.result)
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao iniciar o teste.')
      setBusy(false)
    }
  }

  function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    setError(null)
    const files = Array.from(event.target.files ?? [])
    const { models, resources, unsupported } = classifyFiles(files, MODEL_EXTS)
    if (models.length !== 1) {
      setSelectedModel(null)
      setSelectedResources([])
      setError(models.length === 0 ? 'Selecione um arquivo principal FBX, GLB ou GLTF.' : 'Selecione somente um arquivo principal por importação.')
      return
    }
    if (unsupported.length) {
      setSelectedModel(null)
      setSelectedResources([])
      setError(`Arquivos não suportados na seleção: ${unsupported.map((file) => file.name).join(', ')}`)
      return
    }
    setSelectedModel(models[0])
    setSelectedResources(resources)
    setStatus(`Pronto para importar ${models[0].name}.`)
  }

  function handleBaseFiles(event: ChangeEvent<HTMLInputElement>) {
    setError(null)
    const files = Array.from(event.target.files ?? [])
    const { models, resources, unsupported } = classifyFiles(files, BASE_MODEL_EXTS)
    if (models.length !== 1) {
      setBaseModel(null)
      setBaseResources([])
      setError(models.length === 0 ? 'Selecione uma base FBX, GLB, GLTF ou BLEND.' : 'Selecione somente uma base corporal principal.')
      return
    }
    if (unsupported.length || (extension(models[0].name) === 'blend' && resources.length > 0)) {
      setBaseModel(null)
      setBaseResources([])
      setError(extension(models[0].name) === 'blend' ? 'Envie a base .blend sem dependências externas adicionais.' : `Arquivos não suportados: ${unsupported.map((file) => file.name).join(', ')}`)
      return
    }
    setBaseModel(models[0])
    setBaseResources(resources)
    setStatus(`Base ${models[0].name} pronta para inspeção e adaptação.`)
  }

  async function handleImport() {
    if (!selectedModel) return
    resetTaskUi(`Enviando ${selectedModel.name} ao serviço local...`)
    setAssetResult(null)
    setInspection(null)
    setPreviewUrl(null)
    setPreparationResult(null)
    setPreparedPreviewUrl(null)
    try {
      const { taskId } = await startAssetImport(selectedModel, selectedResources)
      setStatus('Arquivo preservado. Aguardando o Blender...')
      attachTaskSocket(taskId, (event) => {
        if (isAssetImportResult(event.result)) {
          setAssetResult(event.result)
          setInspection(event.result.inspection)
          setPreviewUrl(absoluteAssetUrl(event.result.preview_url))
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao iniciar a importação.')
      setBusy(false)
    }
  }

  async function handlePrepare() {
    if (!assetResult) {
      setError('Importe e inspecione um personagem antes da preparação corporal.')
      return
    }
    if (preparationMode === 'adapt_base' && !baseModel) {
      setError('Selecione a base corporal que será adaptada ao esqueleto Mixamo.')
      return
    }
    resetTaskUi(preparationMode === 'existing_bound' ? 'Validando malha já vinculada ao Mixamo...' : 'Preservando e preparando a base corporal...')
    setPreparationResult(null)
    setPreparedPreviewUrl(null)
    try {
      const response = preparationMode === 'existing_bound'
        ? await startExistingPreparation(assetResult.asset_id)
        : await startAdaptPreparation(assetResult.asset_id, baseModel!, baseResources, adaptOptions)
      attachTaskSocket(response.taskId, (event) => {
        if (isPreparationResult(event.result)) {
          setPreparationResult(event.result)
          setPreparedPreviewUrl(absoluteAssetUrl(event.result.preview_url))
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao iniciar a preparação corporal.')
      setBusy(false)
    }
  }

  function requestView(name: ViewName) {
    setViewRequest((current) => ({ name, nonce: current.nonce + 1 }))
  }

  function updateAdaptOption(key: keyof AdaptBaseOptions, value: string) {
    const number = Number(value)
    setAdaptOptions((current) => ({ ...current, [key]: Number.isFinite(number) ? number : 0 }))
  }

  const viewerToolbar = (
    <div className="viewerToolbar">
      <div className="toolGroup">
        <button onClick={() => requestView('perspective')} title="Perspectiva"><Rotate3D size={16} /> Persp.</button>
        <button onClick={() => requestView('front')}>Frente</button>
        <button onClick={() => requestView('side')}>Lado</button>
        <button onClick={() => requestView('back')}>Trás</button>
      </div>
      <div className="toolGroup">
        <button className={wireframe ? 'active' : ''} onClick={() => setWireframe((value) => !value)}><Waypoints size={16} /> Wireframe</button>
        <button className={showSkeleton ? 'active' : ''} onClick={() => setShowSkeleton((value) => !value)}><Bone size={16} /> Esqueleto</button>
      </div>
    </div>
  )

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brandMark"><Box size={20} /></div>
          <div>
            <strong>Bodiez Local</strong>
            <span>Personalizador 3D · Etapa 3</span>
          </div>
        </div>
        <nav className="topNav" aria-label="Etapas disponíveis">
          <button className={mode === 'import' ? 'active' : ''} onClick={() => setMode('import')}><Cuboid size={15} /> Importar</button>
          <button className={mode === 'prepare' ? 'active' : ''} onClick={() => setMode('prepare')} disabled={!assetResult}><ShieldCheck size={15} /> Preparar base</button>
          <button className={mode === 'blender' ? 'active' : ''} onClick={() => setMode('blender')}><Settings2 size={15} /> Blender</button>
        </nav>
        <div className={`state state-${stateLabel.toLowerCase().replaceAll(' ', '-')}`}>
          <Activity size={15} /> {stateLabel}
        </div>
      </header>

      {mode === 'blender' ? (
        <section className="connectionWorkspace">
          <aside className="sidebar connectionSidebar">
            <p className="eyebrow">Etapa 1 preservada</p>
            <h1>Conexão com o Blender</h1>
            <p className="muted">O navegador conversa somente com o serviço local. O <code>bpy</code> é executado dentro do Blender instalado na máquina.</p>
            <label className="fieldLabel" htmlFor="blenderPath">Executável do Blender</label>
            <div className="pathRow">
              <input id="blenderPath" value={blenderPath} onChange={(event) => setBlenderPath(event.target.value)} placeholder="/usr/bin/blender" spellCheck={false} />
              <button className="iconButton" title="Usar caminho detectado" disabled={!detectedPath || busy} onClick={() => detectedPath && setBlenderPath(detectedPath)}><Search size={18} /></button>
            </div>
            {detectedPath && <p className="hint">Detectado: <code>{detectedPath}</code></p>}
            <div className="buttonRow">
              <button className="secondary" onClick={handleSave} disabled={!blenderPath || busy}><Save size={17} /> Salvar</button>
              <button className="primary" onClick={handleTest} disabled={!blenderPath || busy}><PlugZap size={17} /> {busy ? 'Testando...' : 'Testar Blender'}</button>
            </div>
            <div className="securityNote"><CheckCircle2 size={18} /><div><strong>Execução local protegida</strong><span>Sem shell, sem scripts enviados pelo navegador e com origens locais validadas.</span></div></div>
          </aside>
          <section className="diagnosticStage">
            <div className="stageCard">
              <div className="stageIcon"><Box size={40} /></div>
              <p className="eyebrow">Diagnóstico</p>
              <h2>{status}</h2>
              <div className="progressTrack"><div className="progressFill" style={{ width: `${progress}%` }} /></div>
              <span className="progressText">{progress}%</span>
              {connectionResult && <div className="resultGrid"><div><span>Blender</span><strong>{connectionResult.version}</strong></div><div><span>Python</span><strong>{connectionResult.python_version}</strong></div><div><span>Modo</span><strong>{connectionResult.background ? 'Background' : 'Interface'}</strong></div><div className="wide"><span>Binário</span><strong>{connectionResult.binary_path}</strong></div></div>}
              {error && <div className="errorBox"><CircleAlert size={19} /><span>{error}</span></div>}
            </div>
          </section>
          <aside className="logsPanel"><div className="panelTitle"><TerminalSquare size={18} /> Logs</div><LogList logs={logs} /></aside>
        </section>
      ) : mode === 'prepare' ? (
        <section className="editorWorkspace preparationWorkspace">
          <aside className="sidebar importSidebar preparationSidebar">
            <p className="eyebrow">Etapa 3</p>
            <h1>Preparar base corporal</h1>
            <p className="muted">Valide uma malha já skinnada ou adapte uma base separada. Shape keys e topologia são preservados sempre que possível.</p>

            <div className="assetContext">
              <Bone size={17} />
              <div><strong>{assetResult?.original_name ?? 'Nenhum personagem'}</strong><span>{inspection?.summary.likely_mixamo ? 'Rig provavelmente Mixamo' : 'Compatibilidade Mixamo requer revisão'}</span></div>
            </div>

            <div className="modeCards">
              <button className={preparationMode === 'existing_bound' ? 'active' : ''} onClick={() => setPreparationMode('existing_bound')} disabled={busy}>
                <Link2 size={17} /><strong>Usar malha vinculada</strong><span>Não transfere pesos; valida o skinning existente.</span>
              </button>
              <button className={preparationMode === 'adapt_base' ? 'active' : ''} onClick={() => setPreparationMode('adapt_base')} disabled={busy}>
                <SlidersHorizontal size={17} /><strong>Adaptar outra base</strong><span>Inspeciona, alinha e transfere pesos quando for confiável.</span>
              </button>
            </div>

            {preparationMode === 'adapt_base' && (
              <>
                <button className="dropZone compactDrop" onClick={() => baseInputRef.current?.click()} disabled={busy}>
                  <FileUp size={21} />
                  <strong>{baseModel ? baseModel.name : 'Selecionar base corporal'}</strong>
                  <span>FBX · GLB · GLTF · BLEND</span>
                  <input ref={baseInputRef} type="file" multiple hidden accept=".fbx,.glb,.gltf,.blend,.bin,.png,.jpg,.jpeg,.webp,.ktx2" onChange={handleBaseFiles} />
                </button>
                {baseResources.length > 0 && <p className="hint">Dependências: {baseResources.map((file) => file.name).join(', ')}</p>}

                <div className="assistTitle"><SlidersHorizontal size={15} /> Ajustes assistidos de alinhamento</div>
                <div className="numberGrid">
                  <label>Escala<input type="number" min="0.25" max="4" step="0.01" value={adaptOptions.scale} onChange={(event) => updateAdaptOption('scale', event.target.value)} /></label>
                  <label>Rotação Z<input type="number" min="-180" max="180" step="1" value={adaptOptions.rotation_z} onChange={(event) => updateAdaptOption('rotation_z', event.target.value)} /></label>
                  <label>Offset X<input type="number" min="-10" max="10" step="0.01" value={adaptOptions.offset_x} onChange={(event) => updateAdaptOption('offset_x', event.target.value)} /></label>
                  <label>Offset Y<input type="number" min="-10" max="10" step="0.01" value={adaptOptions.offset_y} onChange={(event) => updateAdaptOption('offset_y', event.target.value)} /></label>
                  <label>Offset Z<input type="number" min="-10" max="10" step="0.01" value={adaptOptions.offset_z} onChange={(event) => updateAdaptOption('offset_z', event.target.value)} /></label>
                </div>
              </>
            )}

            <div className="distinctionNote"><ShieldCheck size={17} /><div><strong>Pesos ≠ retargeting</strong><span>Esta etapa prepara deformação da malha. Conversão/mapeamento de animações fica para a Etapa 5.</span></div></div>
            <button className="primary fullButton" onClick={handlePrepare} disabled={busy || !assetResult || (preparationMode === 'adapt_base' && !baseModel)}><ShieldCheck size={17} /> {busy ? 'Preparando…' : 'Executar preparação e testes'}</button>

            {(busy || progress > 0) && <div className="compactProgress"><div className="progressTrack"><div className="progressFill" style={{ width: `${progress}%` }} /></div><span>{status}</span></div>}
            {(error || viewerError) && <div className="errorBox compact"><CircleAlert size={18} /><span>{error || viewerError}</span></div>}
            {preparationResult && <a className="downloadLink" href={absoluteAssetUrl(preparationResult.blend_url)}><Download size={15} /> Baixar .blend preparado</a>}
          </aside>

          <section className="viewerStage">
            {viewerToolbar}
            <ModelViewer url={currentPreview} wireframe={wireframe} skeleton={showSkeleton} viewRequest={viewRequest} onViewerError={setViewerError} />
            <div className="assetBadge"><Eye size={15} /><span>{preparationResult ? 'Visualizando resultado preparado' : 'Visualizando a cópia importada da Etapa 2'}</span></div>
          </section>

          <aside className="inspectionPanel">
            <div className="panelTitle"><ShieldCheck size={18} /> Validação da base</div>
            <PreparationPanel report={preparationResult?.preparation ?? null} />
            {logs.length > 0 && <details className="logDetails"><summary><TerminalSquare size={15} /> Logs do Blender</summary><LogList logs={logs} /></details>}
          </aside>
        </section>
      ) : (
        <section className="editorWorkspace">
          <aside className="sidebar importSidebar">
            <p className="eyebrow">Etapa 2 preservada</p>
            <h1>Importar personagem</h1>
            <p className="muted">Aceita FBX e GLB/GLTF. O original é arquivado intacto; Blender inspeciona uma cópia e gera um GLB intermediário.</p>

            <button className="dropZone" onClick={() => fileInputRef.current?.click()} disabled={busy}>
              <FileUp size={24} />
              <strong>{selectedModel ? selectedModel.name : 'Selecionar modelo'}</strong>
              <span>FBX · GLB · GLTF</span>
              <input ref={fileInputRef} type="file" multiple hidden accept=".fbx,.glb,.gltf,.bin,.png,.jpg,.jpeg,.webp,.ktx2" onChange={handleFiles} />
            </button>
            {selectedResources.length > 0 && <p className="hint">Dependências GLTF: {selectedResources.map((file) => file.name).join(', ')}</p>}

            <div className="blenderMiniStatus">
              <PlugZap size={16} />
              <div><strong>{blenderPath ? 'Blender configurado' : 'Blender não configurado'}</strong><span>{blenderPath || 'Abra a aba Blender para configurar.'}</span></div>
            </div>

            <button className="primary fullButton" onClick={handleImport} disabled={!selectedModel || !blenderPath || busy}><Upload size={17} /> {busy ? 'Processando…' : 'Importar e inspecionar'}</button>
            {assetResult && <button className="secondary fullButton nextStage" onClick={() => setMode('prepare')}><ShieldCheck size={17} /> Preparar esta base</button>}

            {(busy || progress > 0) && <div className="compactProgress"><div className="progressTrack"><div className="progressFill" style={{ width: `${progress}%` }} /></div><span>{status}</span></div>}
            {(error || viewerError) && <div className="errorBox compact"><CircleAlert size={18} /><span>{error || viewerError}</span></div>}

            <div className="securityNote"><CheckCircle2 size={18} /><div><strong>Original preservado</strong><span>Nenhuma edição destrutiva é aplicada ao arquivo enviado nesta etapa.</span></div></div>
          </aside>

          <section className="viewerStage">
            {viewerToolbar}
            <ModelViewer url={currentPreview} wireframe={wireframe} skeleton={showSkeleton} viewRequest={viewRequest} onViewerError={setViewerError} />
            {assetResult && <div className="assetBadge"><Eye size={15} /><span>Visualizando cópia GLB de <strong>{assetResult.original_name}</strong></span></div>}
          </section>

          <aside className="inspectionPanel">
            <div className="panelTitle"><Bone size={18} /> Recursos detectados</div>
            <InspectionPanel report={inspection} />
            {logs.length > 0 && <details className="logDetails"><summary><TerminalSquare size={15} /> Logs do Blender</summary><LogList logs={logs} /></details>}
          </aside>
        </section>
      )}
    </main>
  )
}

function LogList({ logs }: { logs: LogLine[] }) {
  return (
    <div className="logs">
      {logs.length === 0 ? <p className="empty">Os logs do Blender aparecerão aqui durante o processamento.</p> : logs.map((line, index) => (
        <div className={`logLine log-${line.level}`} key={`${index}-${line.message}`}><span>{line.stream}</span><p>{line.message}</p></div>
      ))}
    </div>
  )
}
