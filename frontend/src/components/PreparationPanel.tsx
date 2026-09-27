import type { PreparationReport } from '../types'

const labels: Record<string, string> = { shoulders: 'Ombros', elbows: 'Cotovelos', hips: 'Quadris', knees: 'Joelhos' }

export default function PreparationPanel({ report }: { report: PreparationReport | null }) {
  if (!report) return <div className="emptyPanel">Execute a preparação para validar rig, pesos, morphs e articulações.</div>
  return <div className="scrollPanel">
    <div className={`notice ${report.ready_for_body_customization ? 'ok' : 'review'}`}><b>{report.ready_for_body_customization ? 'Base pronta para personalização' : 'Revisão assistida necessária'}</b><span>{report.ready_for_body_customization ? 'As validações automáticas desta etapa foram aprovadas.' : 'Há bloqueadores ou pesos que precisam de intervenção.'}</span></div>
    <div className="cards"><div><span>Rig</span><b>{report.target_rig.armature}</b></div><div><span>Mixamo</span><b>{report.target_rig.likely_mixamo ? 'provável' : 'revisar'}</b></div><div><span>Topologia</span><b>{report.preservation.topology_preserved ? 'preservada' : 'alterada'}</b></div><div><span>Pesos</span><b>{report.binding.weight_transfer_performed ? 'transferidos' : report.binding.already_bound ? 'existentes' : 'não aplicados'}</b></div></div>
    <h3>Testes articulares</h3>{Object.entries(labels).map(([key, label]) => { const r = report.joint_validation.regions[key]; return <div className="entity" key={key}><b>{label}: {r?.passed ? 'OK' : 'revisar'}</b>{r?.checks?.map((c, i) => <span key={`${key}-${i}`}>{c.semantic ?? 'osso'}: {c.bone ?? 'não identificado'} · {c.passed ? 'passou' : c.reason ?? 'falhou'}</span>)}</div> })}
    <h3>Vinculação</h3><div className="row"><span>Transferência de pesos</span><b>{report.binding.weight_transfer_performed ? 'sim' : 'não'}</b></div><div className="row"><span>É retargeting?</span><b>não</b></div>{report.binding.transfers?.map((t, i) => <div className="entity" key={i}><b>{t.mesh ?? 'Transferência'}</b><span>{t.performed ? `Cobertura ${Math.round((t.coverage ?? 0) * 100)}%` : t.reason ?? 'não executada'}</span></div>)}
    <h3>Preservação</h3><div className="row"><span>Shape keys antes/depois</span><b>{report.preservation.shape_keys_before ?? report.preservation.shape_keys_preserved ?? 0} / {report.preservation.shape_keys_after ?? report.preservation.shape_keys_preserved ?? 0}</b></div><div className="row"><span>Operação destrutiva</span><b>{report.preservation.destructive_modifiers_applied ? 'sim' : 'não'}</b></div>
    {report.blockers.map(item => <div className="errorLine" key={item}>{item}</div>)}{report.warnings.map(item => <div className="warningLine" key={item}>{item}</div>)}
    <div className="warning">{report.limitations.map(item => <p key={item}>{item}</p>)}</div>
  </div>
}
