import { AlertTriangle, Bone, CheckCircle2, ChevronDown, Link2, ShieldCheck, SlidersHorizontal, XCircle } from 'lucide-react'
import type { PreparationReport } from '../types'

type Props = { report: PreparationReport | null }

function pct(value?: number) {
  return value == null ? '—' : `${Math.round(value * 100)}%`
}

const regionLabels: Record<string, string> = {
  shoulders: 'Ombros',
  elbows: 'Cotovelos',
  hips: 'Quadris',
  knees: 'Joelhos',
}

export default function PreparationPanel({ report }: Props) {
  if (!report) {
    return (
      <div className="inspectionEmpty">
        <ShieldCheck size={22} />
        <strong>Preparação da base corporal</strong>
        <span>Escolha usar a malha já vinculada ou adaptar outra base. O Blender verificará rig, pesos, morphs e deformação real antes de liberar a próxima etapa.</span>
      </div>
    )
  }

  return (
    <div className="inspectionScroll">
      <div className={`readiness ${report.ready_for_body_customization ? 'ready' : 'review'}`}>
        {report.ready_for_body_customization ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
        <div>
          <strong>{report.ready_for_body_customization ? 'Base pronta para personalização' : 'Revisão assistida necessária'}</strong>
          <span>{report.ready_for_body_customization ? 'Rig e articulações passaram pelas validações desta etapa.' : 'O arquivo foi preservado e preparado, mas existem bloqueadores ou pesos que precisam de intervenção.'}</span>
        </div>
      </div>

      <section className="summaryCards">
        <div><span>Rig alvo</span><strong>{report.target_rig.armature}</strong></div>
        <div><span>Mixamo</span><strong>{report.target_rig.likely_mixamo ? 'provável' : 'revisar'}</strong></div>
        <div><span>Topologia</span><strong>{report.preservation.topology_preserved ? 'preservada' : 'alterada'}</strong></div>
        <div><span>Pesos</span><strong>{report.binding.weight_transfer_performed ? 'transferidos' : report.binding.already_bound ? 'existentes' : 'não aplicados'}</strong></div>
      </section>

      <details open>
        <summary><Bone size={16} /> Testes articulares <ChevronDown size={14} /></summary>
        <div className="detailBody jointGrid">
          {Object.entries(regionLabels).map(([key, label]) => {
            const region = report.joint_validation.regions[key]
            return (
              <div className={`jointCard ${region?.passed ? 'pass' : 'fail'}`} key={key}>
                <div>{region?.passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />}<strong>{label}</strong></div>
                {region?.checks?.length ? region.checks.map((check) => (
                  <span key={check.semantic}>{check.semantic}: {check.bone ?? 'não mapeado'} · {check.passed ? 'OK' : 'revisar'}</span>
                )) : <span>Teste não executado.</span>}
              </div>
            )
          })}
        </div>
      </details>

      <details open>
        <summary><Link2 size={16} /> Vinculação e pesos <ChevronDown size={14} /></summary>
        <div className="detailBody">
          <div className="kv"><span>Transferência de pesos</span><b>{report.binding.weight_transfer_performed ? 'executada' : 'não executada'}</b></div>
          <div className="kv"><span>É retargeting?</span><b>Não</b></div>
          {report.binding.transfers?.map((transfer, index) => (
            <div className="entityCard" key={`${transfer.mesh ?? 'transfer'}-${index}`}>
              <strong>{transfer.mesh ?? 'Transferência'}</strong>
              <div className="kv"><span>Cobertura</span><b>{pct(transfer.coverage)}</b></div>
              <div className="kv"><span>Distância média</span><b>{transfer.mean_reference_distance ?? '—'}</b></div>
              {transfer.reason && <p className="smallMuted">{transfer.reason}</p>}
            </div>
          ))}
          {report.binding.meshes?.map((mesh) => (
            <div className="listLine" key={mesh.mesh}><span>{mesh.mesh}</span><b>{pct(mesh.coverage)}</b></div>
          ))}
        </div>
      </details>

      <details>
        <summary><SlidersHorizontal size={16} /> Base e preservação <ChevronDown size={14} /></summary>
        <div className="detailBody">
          <div className="kv"><span>Shape keys antes</span><b>{report.preservation.shape_keys_before ?? report.preservation.shape_keys_preserved ?? 0}</b></div>
          <div className="kv"><span>Shape keys depois</span><b>{report.preservation.shape_keys_after ?? report.preservation.shape_keys_preserved ?? 0}</b></div>
          <div className="kv"><span>Drivers observados</span><b>{report.preservation.drivers_before ?? report.preservation.drivers_observed ?? 0}</b></div>
          <div className="kv"><span>Modificadores destrutivos aplicados</span><b>{report.preservation.destructive_modifiers_applied ? 'sim' : 'não'}</b></div>
          {report.base_inspection && (
            <>
              <div className="kv"><span>Objetos da base</span><b>{report.base_inspection.before.objects.length}</b></div>
              <div className="kv"><span>Armatures próprios</span><b>{report.base_inspection.before.armature_count}</b></div>
              <div className="kv"><span>Drivers</span><b>{report.base_inspection.before.driver_count}</b></div>
              {report.base_inspection.before.meshes.map((mesh) => (
                <div className="entityCard" key={mesh.name}>
                  <strong>{mesh.name}</strong>
                  <div className="kv"><span>Vértices</span><b>{mesh.vertices.toLocaleString('pt-BR')}</b></div>
                  <div className="kv"><span>Shape keys</span><b>{mesh.shape_key_count}</b></div>
                  <div className="kv"><span>Drivers de morph</span><b>{mesh.shape_key_drivers}</b></div>
                </div>
              ))}
            </>
          )}
        </div>
      </details>

      {(report.blockers.length > 0 || report.warnings.length > 0) && (
        <div className="issueStack">
          {report.blockers.map((item) => <div className="issue blocker" key={item}><XCircle size={14} /><span>{item}</span></div>)}
          {report.warnings.map((item) => <div className="issue warning" key={item}><AlertTriangle size={14} /><span>{item}</span></div>)}
        </div>
      )}

      <div className="limitations">
        <AlertTriangle size={16} />
        <div>
          <strong>Limitações reais</strong>
          {report.limitations.map((item) => <p key={item}>{item}</p>)}
        </div>
      </div>
    </div>
  )
}
