import type { InspectionReport } from '../types'

export default function InspectionPanel({ report }: { report: InspectionReport | null }) {
  if (!report) return <div className="emptyPanel">A inspeção real do Blender aparecerá aqui após a importação.</div>
  return <div className="scrollPanel">
    <div className="cards"><div><span>Malhas</span><b>{report.summary.mesh_count}</b></div><div><span>Armatures</span><b>{report.summary.armature_count}</b></div><div><span>Shape keys</span><b>{report.summary.shape_key_count}</b></div><div><span>Actions</span><b>{report.summary.action_count}</b></div></div>
    <div className="notice"><b>{report.summary.likely_mixamo ? 'Estrutura provavelmente Mixamo' : 'Mixamo não confirmado'}</b><span>A detecção é heurística; não há conversão automática de rig.</span></div>
    <h3>Malhas</h3>{report.meshes.map(mesh => <div className="entity" key={mesh.name}><b>{mesh.name}</b><span>{mesh.vertices.toLocaleString('pt-BR')} vértices · pesos {Math.round(mesh.weights.coverage * 100)}% · {Math.max(0, mesh.shape_keys.length - 1)} morphs</span></div>)}
    <h3>Esqueleto</h3>{report.armatures.map(arm => <div className="entity" key={arm.name}><b>{arm.name}</b><span>{arm.bone_count} ossos · prefixo {arm.bone_name_analysis.namespace_prefix ?? 'nenhum'} · {arm.bone_name_analysis.canonical_mixamo_matches}/{arm.bone_name_analysis.canonical_mixamo_total} nomes canônicos</span></div>)}
    <h3>Materiais</h3>{report.materials.map(m => <div className="row" key={m.name}><span>{m.name}</span><b>{m.use_nodes ? 'Nodes' : 'Legacy'}</b></div>)}
    <h3>Animações</h3>{report.animations.actions.length ? report.animations.actions.map(a => <div className="row" key={a.name}><span>{a.name}</span><b>{a.frame_range.join('–')}</b></div>) : <span className="muted">Nenhuma Action.</span>}
    <div className="warning">{report.limitations.map(item => <p key={item}>{item}</p>)}</div>
  </div>
}
