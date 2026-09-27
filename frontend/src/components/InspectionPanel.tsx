import { AlertTriangle, Bone, Boxes, ChevronDown, Film, Layers3 } from 'lucide-react'
import type { InspectionReport } from '../types'

type Props = { report: InspectionReport | null }

function pct(value: number) {
  return `${Math.round(value * 100)}%`
}

export default function InspectionPanel({ report }: Props) {
  if (!report) {
    return (
      <div className="inspectionEmpty">
        <Layers3 size={22} />
        <strong>Inspeção do arquivo</strong>
        <span>Os dados reais de malha, rig, pesos, materiais, shape keys e animações aparecerão aqui após o Blender processar o arquivo.</span>
      </div>
    )
  }

  return (
    <div className="inspectionScroll">
      <section className="summaryCards">
        <div><span>Malhas</span><strong>{report.summary.mesh_count}</strong></div>
        <div><span>Armatures</span><strong>{report.summary.armature_count}</strong></div>
        <div><span>Shape keys</span><strong>{report.summary.shape_key_count}</strong></div>
        <div><span>Animações</span><strong>{report.summary.action_count}</strong></div>
      </section>

      <div className={`mixamoStatus ${report.summary.likely_mixamo ? 'ok' : 'neutral'}`}>
        <Bone size={17} />
        <div>
          <strong>{report.summary.likely_mixamo ? 'Estrutura provavelmente Mixamo' : 'Mixamo não confirmado'}</strong>
          <span>Resultado heurístico; nenhuma conversão ou retargeting é feita nesta etapa.</span>
        </div>
      </div>

      <details open>
        <summary><Boxes size={16} /> Malhas <ChevronDown size={14} /></summary>
        <div className="detailBody">
          {report.meshes.length === 0 && <p className="smallMuted">Nenhuma malha encontrada.</p>}
          {report.meshes.map((mesh) => (
            <div className="entityCard" key={mesh.name}>
              <strong>{mesh.name}</strong>
              <div className="kv"><span>Vértices</span><b>{mesh.vertices.toLocaleString('pt-BR')}</b></div>
              <div className="kv"><span>Polígonos</span><b>{mesh.polygons.toLocaleString('pt-BR')}</b></div>
              <div className="kv"><span>Armature</span><b>{mesh.armature ?? 'nenhum'}</b></div>
              <div className="kv"><span>Cobertura de pesos</span><b>{pct(mesh.weights.coverage)}</b></div>
              <div className="kv"><span>Influências médias</span><b>{mesh.weights.average_influences}</b></div>
              <div className="tagRow">
                {mesh.shape_keys.filter((key) => !key.basis).map((key) => <span className="tag" key={key.name}>{key.name}</span>)}
                {mesh.shape_keys.length <= 1 && <span className="tag mutedTag">sem morphs</span>}
              </div>
            </div>
          ))}
        </div>
      </details>

      <details open>
        <summary><Bone size={16} /> Esqueleto <ChevronDown size={14} /></summary>
        <div className="detailBody">
          {report.armatures.length === 0 && <p className="smallMuted">Nenhum armature encontrado.</p>}
          {report.armatures.map((armature) => (
            <div className="entityCard" key={armature.name}>
              <strong>{armature.name}</strong>
              <div className="kv"><span>Ossos</span><b>{armature.bone_count}</b></div>
              <div className="kv"><span>Raiz(es)</span><b>{armature.roots.join(', ') || '—'}</b></div>
              <div className="kv"><span>Prefixo/namespace</span><b>{armature.bone_name_analysis.namespace_prefix ?? 'nenhum'}</b></div>
              <div className="kv"><span>Correspondências Mixamo</span><b>{armature.bone_name_analysis.canonical_mixamo_matches}/{armature.bone_name_analysis.canonical_mixamo_total}</b></div>
              <div className="semanticMap">
                {Object.entries(armature.bone_name_analysis.semantic_matches).map(([semantic, bone]) => (
                  <div key={semantic}><span>{semantic}</span><b>{bone}</b></div>
                ))}
              </div>
              <div className="boneList">
                {armature.bones.map((bone) => (
                  <span key={bone.name} title={bone.parent ? `Pai: ${bone.parent}` : 'Osso raiz'}>{bone.name}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </details>

      <details>
        <summary><Layers3 size={16} /> Materiais <ChevronDown size={14} /></summary>
        <div className="detailBody">
          {report.materials.length === 0 ? <p className="smallMuted">Nenhum material encontrado.</p> : report.materials.map((material) => (
            <div className="listLine" key={material.name}><span>{material.name}</span><b>{material.use_nodes ? 'Nodes' : 'Legacy'}</b></div>
          ))}
        </div>
      </details>

      <details>
        <summary><Film size={16} /> Animações <ChevronDown size={14} /></summary>
        <div className="detailBody">
          {report.animations.actions.length === 0 ? <p className="smallMuted">Nenhuma Action encontrada.</p> : report.animations.actions.map((action) => (
            <div className="listLine" key={action.name}><span>{action.name}</span><b>{action.frame_range[0]}–{action.frame_range[1]}</b></div>
          ))}
          <div className="kv"><span>FPS da cena</span><b>{report.animations.fps}</b></div>
        </div>
      </details>

      <div className="limitations">
        <AlertTriangle size={16} />
        <div>
          <strong>Limites desta etapa</strong>
          {report.limitations.map((item) => <p key={item}>{item}</p>)}
        </div>
      </div>
    </div>
  )
}
