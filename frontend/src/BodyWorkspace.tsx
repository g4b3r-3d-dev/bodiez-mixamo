import { useEffect,useMemo,useRef,useState } from 'react'
import { ArrowLeft,Download,RefreshCw,RotateCcw,Save,SlidersHorizontal,TriangleAlert } from 'lucide-react'
import ModelViewer, {type BreastMarkers, type MarkerDraft} from './components/ModelViewer'
import './components/body.css'

type Ready={asset_id:string;preparation_id:string;mode:string|null;updated_at:number;name?:string}
type Values=Record<string,number>;type Bindings=Record<string,string|undefined>
type Spec={label:string;kind:string;min:number;max:number;default:number}
type Source={source_id:string;type:string;display_name:string;control_hint:string|null;driven:boolean;slider_min:number;slider_max:number}
type MarkerInfo={height:number;radius_min:number;radius_max:number;radius_default:number}
type Caps={breast_marker_info?:MarkerInfo;controls:Record<string,{enabled:boolean;engine?:string;reason?:string|null;generated_assisted?:boolean;requires_markers?:boolean}>;morph_sources:Source[];default_bindings:Bindings;control_specs:Record<string,Spec>;builtin_presets:Record<string,Values>;limitations?:string[];armature?:string}
type Event={type:string;value?:number;message:string;result?:any}
const API='http://127.0.0.1:8000',WS='ws://127.0.0.1:8000'
const structural=['height','head_size','shoulder_width','hip_width','arm_length','leg_length']
const morphs=['arm_volume','leg_volume','torso_volume','breast_size']
const defaults=():Values=>({feminine_curves:0,height:1,head_size:1,shoulder_width:1,hip_width:1,arm_length:1,leg_length:1,arm_volume:0,leg_volume:0,torso_volume:0,breast_size:0})
async function req(path:string,init?:RequestInit){const r=await fetch(API+path,init);if(!r.ok){let m=`HTTP ${r.status}`;try{m=(await r.json()).detail??m}catch{}throw new Error(m)}return r.json()}
function watch(id:string,on:(e:Event)=>void){const s=new WebSocket(`${WS}/ws/tasks/${id}`);s.onopen=()=>s.send('ready');s.onmessage=e=>on(JSON.parse(e.data));return s}
export default function BodyWorkspace({onBack}:{onBack:()=>void}){
 const [ready,setReady]=useState<Ready[]>([]),[key,setKey]=useState(''),[caps,setCaps]=useState<Caps|null>(null),[bodyId,setBodyId]=useState<string|null>(null),[values,setValues]=useState<Values>(defaults()),[bindings,setBindings]=useState<Bindings>({}),[customPresets,setCustomPresets]=useState<Record<string,any>>({}),[presetName,setPresetName]=useState(''),[preview,setPreview]=useState<string|null>(null),[blend,setBlend]=useState<string|null>(null),[status,setStatus]=useState('Selecione uma preparação aprovada.'),[progress,setProgress]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null)
 const [baseline,setBaseline]=useState<string|null>(null),[before,setBefore]=useState(false),[autoApply,setAutoApply]=useState(true),[applied,setApplied]=useState(''),[skeleton,setSkeleton]=useState(false),[view,setView]=useState<{name:'front'|'side'|'perspective';nonce:number}>({name:'front',nonce:0})
 const [breastMarkers,setBreastMarkers]=useState<BreastMarkers|null>(null),[markerDraft,setMarkerDraft]=useState<MarkerDraft|null>(null),[activeMarker,setActiveMarker]=useState<'left'|'right'|null>(null)
 const [adjustments,setAdjustments]=useState<string[]>([])
 const marking=markerDraft!==null
 const socket=useRef<WebSocket|null>(null)
 const snapshot=JSON.stringify({values,bindings,breast_markers:breastMarkers})
 const dirty=!!caps&&snapshot!==applied
 useEffect(()=>()=>{socket.current?.close()},[])
 const selected=useMemo(()=>ready.find(x=>`${x.asset_id}:${x.preparation_id}`===key)??null,[ready,key])
 const refresh=async()=>{try{const x=await req('/api/stage4/ready-preparations');setReady(x.items);if(!key&&x.items[0])setKey(`${x.items[0].asset_id}:${x.items[0].preparation_id}`)}catch(e){setError(String(e))}}
 useEffect(()=>{void refresh()},[])
 const run=(id:string,done:(r:any)=>void)=>{
  socket.current?.close()
  let finished=false
  const s=watch(id,e=>{
   if(socket.current!==s)return
   if(e.type==='progress'){setStatus(e.message);setProgress(e.value??0)}
   if(e.type==='error'){finished=true;setError(e.message);setStatus('Não foi possível aplicar. Ajuste e tente novamente.');setBusy(false);s.close()}
   if(e.type==='success'){finished=true;done(e.result);setStatus(e.message);setProgress(100);setBusy(false);s.close()}
  })
  socket.current=s
  s.onclose=()=>{if(socket.current===s&&!finished){setError('Conexão interrompida antes da conclusão. Tente novamente.');setBusy(false)}}
  s.onerror=()=>s.close()
 }
 const prepare=async()=>{
  if(!selected)return
  setBusy(true);setError(null);setAdjustments([]);setProgress(0);setCaps(null);setPreview(null);setBaseline(null);setBlend(null);setBefore(false);setApplied('');setCustomPresets({});setStatus('Preparando controles e prévia…');setBreastMarkers(null);setMarkerDraft(null);setActiveMarker(null)
  try{
   const x=await req(`/api/assets/${selected.asset_id}/preparations/${selected.preparation_id}/customizations`,{method:'POST'})
   setBodyId(x.customization_id)
   run(x.task_id,r=>{
    const v=defaults(),b=r.capabilities.default_bindings??{},url=API+r.preview_url+`?v=${Date.now()}`
    setCaps(r.capabilities);setBindings(b);setValues(v);setApplied(JSON.stringify({values:v,bindings:b,breast_markers:null}));setPreview(url);setBaseline(url)
    void req(`/api/assets/${selected.asset_id}/preparations/${selected.preparation_id}/customizations/${r.customization_id}/presets`).then(p=>setCustomPresets(p.custom??{})).catch(e=>setError(String(e)))
   })
  }catch(e){setError(String(e));setBusy(false)}
 }
 const apply=async()=>{
  if(!selected||!bodyId||busy||marking)return
  const sent=snapshot
  setBusy(true);setError(null);setProgress(0);setStatus('Aplicando alterações no corpo…')
  try{
   const x=await req(`/api/assets/${selected.asset_id}/preparations/${selected.preparation_id}/customizations/${bodyId}/apply`,{method:'POST',headers:{'Content-Type':'application/json'},body:sent})
   run(x.task_id,r=>{
    const effective=r.values??values,b=r.bindings??bindings,markers=r.breast_markers??null
    setValues(effective);setBindings(b);setBreastMarkers(markers)
    setAdjustments(Object.keys(r.application?.natural_shape?.adjustments??{}).map(k=>caps?.control_specs[k]?.label??k))
    setPreview(API+r.preview_url+`?v=${Date.now()}`);setBlend(API+r.blend_url)
    setApplied(JSON.stringify({values:effective,bindings:b,breast_markers:markers}));setBefore(false)
   })
  }catch(e){setError(String(e));setBusy(false)}
 }
 useEffect(()=>{
  if(!autoApply||!dirty||busy||error||!bodyId||marking)return
  const timer=window.setTimeout(()=>void apply(),750)
  return()=>window.clearTimeout(timer)
 },[snapshot,autoApply,dirty,busy,error,bodyId,marking])
 const save=async()=>{if(!selected||!bodyId||!presetName.trim())return;try{await req(`/api/assets/${selected.asset_id}/preparations/${selected.preparation_id}/customizations/${bodyId}/presets`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:presetName,values,bindings,breast_markers:breastMarkers})});const p=await req(`/api/assets/${selected.asset_id}/preparations/${selected.preparation_id}/customizations/${bodyId}/presets`);setCustomPresets(p.custom??{});setPresetName('')}catch(e){setError(String(e))}}
 const download=()=>{const b=new Blob([JSON.stringify({format_version:2,values,bindings,breast_markers:breastMarkers},null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='bodiez-body-preset.json';a.click();URL.revokeObjectURL(a.href)}
 const setPreset=(p:any)=>{
  const b=p.bindings??bindings,next={...defaults(),...(p.values??p)}
  for(const n of Object.keys(next)){if(!caps?.controls[n]?.enabled&&!b[n])next[n]=defaults()[n];const spec=caps?.control_specs[n];if(spec)next[n]=Math.max(spec.min,Math.min(spec.max,next[n]))}
  setValues(next);setBindings(b);if('breast_markers' in p)setBreastMarkers(p.breast_markers)
  setBefore(false);setError(null)
 }
 const startMarkers=()=>{
  if(!caps?.breast_marker_info||busy)return
  setMarkerDraft(breastMarkers??{radius:caps.breast_marker_info.radius_default});setActiveMarker('left');setBefore(true);setError(null)
  setView(v=>({name:'front',nonce:v.nonce+1}))
 }
 const finishMarkers=()=>{
  if(!markerDraft?.left||!markerDraft.right)return
  setBreastMarkers(markerDraft as BreastMarkers);setBindings(b=>({...b,breast_size:'markers:breast_size'}))
  setMarkerDraft(null);setActiveMarker(null);setBefore(false);setError(null)
 }
 return <div className="stage4Shell"><header className="stage4Topbar"><button className="secondary" onClick={onBack}><ArrowLeft size={15}/> Etapas 1–3</button><div><strong>Corpo · Etapa 4</strong><span>Personalize e compare o corpo na mesma câmera</span></div></header>
 <aside className="stage4Left panel"><div className="panelTitle">Base preparada</div><button className="secondary" onClick={()=>void refresh()}><RefreshCw size={14}/> Atualizar</button><select aria-label="Base preparada" disabled={busy||marking} value={key} onChange={e=>{setKey(e.target.value);setBodyId(null);setCaps(null);setPreview(null);setBaseline(null);setBlend(null);setApplied('');setBreastMarkers(null);setMarkerDraft(null);setActiveMarker(null)}}><option value="">Selecione…</option>{ready.map(x=><option key={`${x.asset_id}:${x.preparation_id}`} value={`${x.asset_id}:${x.preparation_id}`}>{x.name??x.asset_id.slice(0,8)} · {new Date(x.updated_at*1000).toLocaleString('pt-BR')}</option>)}</select><button className="primary" disabled={!selected||busy||marking} onClick={()=>void prepare()}><SlidersHorizontal size={15}/> Preparar controles</button><div className="progress"><div style={{width:`${progress}%`}}/></div><p className="muted" role="status">{status}</p><label className="bodyAuto"><input type="checkbox" checked={autoApply} onChange={e=>setAutoApply(e.target.checked)}/> Aplicar automaticamente</label>{caps&&<p className="bodyPending">{busy?'Processando alterações…':dirty?'Alterações ainda não aplicadas':'Prévia corresponde aos valores aplicados'}</p>}{error&&<div className="errorBox">{error}</div>}{blend&&<a className="downloadLink" href={blend}><Download size={14}/> Baixar .blend personalizado</a>}</aside>
 <main className="stage4Viewer">
 <div className="bodyViewTools"><button disabled={!baseline||marking} onClick={()=>setBefore(x=>!x)}>{before?'Mostrar depois':'Mostrar antes'}</button>{(['front','side','perspective'] as const).map((name,i)=><button key={name} onClick={()=>setView(v=>({name,nonce:v.nonce+1}))}>{['Frente','Lado','Perspectiva'][i]}</button>)}<label><input type="checkbox" checked={skeleton} onChange={e=>setSkeleton(e.target.checked)}/> Ossos</label></div>
 {marking&&markerDraft&&caps?.breast_marker_info&&<div className="bodyMarkerTools" role="region" aria-label="Marcar seios">
 <strong>Marque o centro de cada seio no modelo</strong><p>Os lados são os do personagem: na vista frontal, o esquerdo aparece à sua direita. Clique para marcar; arraste para girar e use a roda para aproximar.</p>
 <div className="markerSideButtons">{(['left','right'] as const).map(side=><button className={side===activeMarker?'selected':''} aria-pressed={side===activeMarker} key={side} onClick={()=>setActiveMarker(side)}>{side==='left'?'1 · Esquerdo':'2 · Direito'} {markerDraft[side]?'✓':''}</button>)}</div>
 <label>Área de influência · {Math.round(markerDraft.radius/caps.breast_marker_info.height*100)}% da altura<input aria-label="Área de influência dos seios" type="range" min={caps.breast_marker_info.radius_min} max={caps.breast_marker_info.radius_max} step={caps.breast_marker_info.height*.001} value={markerDraft.radius} onChange={e=>setMarkerDraft(d=>d?{...d,radius:Number(e.target.value)}:d)}/></label>
 <button disabled={!markerDraft.left||!markerDraft.right} onClick={finishMarkers}>Usar marcadores</button><button onClick={()=>{setMarkerDraft(null);setActiveMarker(null);setBefore(false)}}>Cancelar marcação</button>
 </div>}
 <div className="bodyCanvas"><ModelViewer key={bodyId} url={marking||before?baseline:preview} wireframe={false} skeleton={skeleton} preserveCamera anatomicalView onViewerError={setError} viewRequest={view} markerDraft={markerDraft} activeMarker={activeMarker} onMarkerPick={(side,point)=>{setMarkerDraft(d=>d?{...d,[side]:point}:d);setActiveMarker(side==='left'?'right':'left');setError(null)}}/><span className="bodyCompareLabel">{marking?'MARCAÇÃO · base original':before?'ANTES · base original':dirty?'DEPOIS · última aplicação (alterações pendentes)':'DEPOIS · valores aplicados'}</span></div>
 </main>
 <aside className="stage4Right panel bodyControlsPanel">{!caps?<div className="emptyPanel"><SlidersHorizontal size={28}/><strong>Controles ainda não inspecionados</strong><span>O Blender precisa descobrir o que realmente existe nesta base.</span></div>:<>
 <section className="bodySection"><strong>Proporções naturais · ativo</strong><p className="microNote">Os ajustes preservam as características da base e são moderados em conjunto para evitar deformações excessivas, inclusive nos seios.</p>{adjustments.length>0&&!dirty&&<p className="microNote" role="status">Ajustes reduzidos para preservar a forma: {adjustments.join(", ")}. Os controles mostram os valores aplicados.</p>}</section>
 <section className="bodySection"><div className="sectionHeading"><span>Tipos corporais</span><small>presets</small></div><div className="presetGrid">{Object.entries(caps.builtin_presets).map(([n,p])=><button key={n} onClick={()=>setPreset(p)} disabled={busy||marking}>{n}</button>)}</div><p className="microNote">“Musculoso” ajusta volume/proporção; não inventa definição muscular ausente.</p></section>
 <section className="bodySection bodyCurves">
  <div className="sectionHeading"><span>Curvas femininas</span><small>silhueta</small></div>
  {caps.control_specs.feminine_curves?<>
   <Slider name="feminine_curves" caps={caps} values={values} busy={busy||marking} setValues={f=>{
    setValues(f);setBindings(b=>({...b,feminine_curves:caps.default_bindings.feminine_curves}));setBefore(false);setError(null)
   }}/>
   {caps.controls.feminine_curves?.enabled&&<div className="curveLevels">
    {([['Original',0],['Suaves',.35],['Marcadas',.65],['Máximas',1]] as const).map(([label,level])=>
     <button key={label} disabled={busy||marking} aria-pressed={values.feminine_curves===level} onClick={()=>{
      setValues(v=>({...v,feminine_curves:level}));setBindings(b=>({...b,feminine_curves:caps.default_bindings.feminine_curves}));setBefore(false);setError(null)
     }}>{label}</button>
    )}
   </div>}
  </>:<p className="microNote">Prepare os controles novamente para habilitar este ajuste.</p>}
  <p className="microNote">Afina a cintura e acentua quadris e glúteos. 0% mantém a silhueta original deste ajuste; 100% solicita a intensidade máxima, sujeita à preservação da forma. Os seios têm um controle separado abaixo.</p>
 </section>
 <section className="bodySection"><div className="sectionHeading"><span>Estrutura</span><small>rig</small></div>{structural.map(n=><Slider key={n} name={n} caps={caps} values={values} setValues={setValues} busy={busy||marking}/>)}</section>
 <section className="bodySection"><div className="sectionHeading"><span>Volume e silhueta</span><small>shape keys</small></div>{morphs.map(n=>{const cap=caps.controls[n],selectedSource=bindings[n]??'',options=caps.morph_sources.filter(s=>!s.driven&&(s.type==='existing'||(s.control_hint===n&&(s.type!=='markers'||breastMarkers))));return <div className="morphControl" key={n}><div className="morphHeader"><strong>{caps.control_specs[n].label}</strong>{cap.generated_assisted&&<span className="generatedPill">assistido</span>}</div><select aria-label={`${caps.control_specs[n].label} · fonte`} disabled={busy||marking} value={selectedSource} onChange={e=>{setBindings(x=>({...x,[n]:e.target.value||''}));setValues(x=>({...x,[n]:caps.control_specs[n].default}));if(n==='breast_size'&&!e.target.value)setBreastMarkers(null);setError(null)}}><option value="">{'Sem fonte de morph'}</option>{options.map(s=><option key={s.source_id} value={s.source_id}>{s.type==='existing'?'Existente':'Assistido'} · {s.display_name}</option>)}</select>{selectedSource?<Slider name={n} caps={caps} values={values} setValues={setValues} busy={busy||marking} source={caps.morph_sources.find(s=>s.source_id===selectedSource)} compact/>:<div className="controlUnavailable"><TriangleAlert size={14}/><span>{cap.reason??'Mapeie uma fonte real.'}</span></div>}{n==='breast_size'&&caps.breast_marker_info&&<div className="breastMarkerSetup"><button className="secondary" disabled={busy||marking} onClick={startMarkers}>{breastMarkers?'Reposicionar marcadores':'Marcar posição dos seios'}</button><p className="microNote">{cap.requires_markers?'Sem ossos dos seios: marque o centro de cada seio na superfície do modelo.':'Ossos dos seios detectados. Você também pode definir a região por marcadores.'}</p>{breastMarkers&&<span className="microNote">Ajuste o volume: valores negativos reduzem, positivos aumentam e 0 restaura o original.</span>}</div>}</div>})}</section>
 <section className="bodySection"><div className="sectionHeading"><span>Presets JSON</span><small>local</small></div>{Object.keys(customPresets).length>0&&<select disabled={busy||marking} defaultValue="" onChange={e=>e.target.value&&setPreset(customPresets[e.target.value])}><option value="">Carregar salvo…</option>{Object.keys(customPresets).sort().map(n=><option key={n}>{n}</option>)}</select>}<div className="presetSaveRow"><input value={presetName} onChange={e=>setPresetName(e.target.value)} placeholder="Nome do preset"/><button disabled={busy||marking} onClick={()=>void save()}><Save size={15}/></button><button onClick={download}><Download size={15}/></button></div></section>
 <div className="bodyActions"><button className="secondary" disabled={busy||marking} onClick={()=>{setValues(defaults());setBindings(caps.default_bindings??{});setBreastMarkers(null);setError(null);setBefore(false)}}><RotateCcw size={15}/> Restaurar</button><button className="primary" disabled={busy||marking||!dirty} onClick={()=>void apply()}><SlidersHorizontal size={15}/> Aplicar no Blender</button></div><p className="microNote">Com aplicação automática ligada, a prévia atualiza após parar de ajustar. Use Mostrar antes para comparar. O volume é uma intensidade de deformação assistida, não uma medida anatômica.</p>{caps.limitations?.map(x=><p className="microNote" key={x}>{x}</p>)}</>}</aside></div>
}
function Slider({name,caps,values,setValues,busy,compact=false,source}:{name:string;caps:Caps;values:Values;setValues:(f:any)=>void;busy:boolean;compact?:boolean;source?:Source}){const s=caps.control_specs[name],c=caps.controls[name];if(!c.enabled&&!compact)return <div className="disabledControl"><strong>{s.label}</strong><span>{c.reason??'Indisponível.'}</span></div>;const v=values[name]??s.default;return <label className="bodySlider"><div><span>{s.label}</span><strong>{s.kind==='structural'?Math.round(v*100)+'%':(s.min<0&&v>=0?'+':'')+Math.round(v*100)+'%'}</strong></div><input aria-label={s.label} type="range" min={source?Math.max(s.min,source.slider_min):s.min} max={source?Math.min(s.max,source.slider_max):s.max} step="0.01" value={v} disabled={busy} onChange={e=>setValues((x:Values)=>({...x,[name]:Number(e.target.value)}))}/></label>}
